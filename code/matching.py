"""Finding pickup/dropoff points and the best driver for a walker."""
from typing import List, Optional, Tuple

import config
from AgentState import AgentState
from agents import create_agent
from geo import LatLon, is_within_dist, topk_by_haversine
from Match import Match, MatchLight
from MatchSimulation import MatchSimulation
from osrm_client import build_walker_route_full, walk_fast
from status import Status


# ---------------------------------------------------- pickup / dropoff points

def find_pickup_light(driver: AgentState, walker_pos: LatLon,
                      k: int = config.PICKUP_CANDIDATES):
    """Point on the driver's REMAINING route with the shortest walk from walker_pos.
    Returns (point, walk_m, walk_s, index)."""
    pts = driver.route.geometry_latlon
    start_index = driver.idx

    tail = pts[start_index:]
    if not tail:
        raise RuntimeError("Driver at end")

    cand_idx = [start_index + j for j in topk_by_haversine(tail, walker_pos, k)]

    best_i = None
    best_m = float("inf")
    best_s = float("inf")
    for i in cand_idx:
        m, s = walk_fast(walker_pos, pts[i])  # pos -> pickup
        if m < best_m:
            best_m, best_s, best_i = m, s, i
    if best_i is None:
        raise RuntimeError("No pickup point found")
    return pts[best_i], best_m, best_s, best_i


def find_dropoff_light(driver: AgentState, walker_dest: LatLon, pickup_i: int,
                       k: int = config.DROPOFF_CANDIDATES):
    """Point AFTER the pickup with the shortest walk to walker_dest.
    Returns (point, walk_m, walk_s, index)."""
    pts = driver.route.geometry_latlon
    tail = pts[pickup_i + 1:]
    if not tail:
        raise RuntimeError("Pickup at end")

    cand_idx = [pickup_i + 1 + j for j in topk_by_haversine(tail, walker_dest, k)]

    best_i = None
    best_m = float("inf")
    best_s = float("inf")
    for i in cand_idx:
        m, s = walk_fast(pts[i], walker_dest)  # dropoff -> dest
        if m < best_m:
            best_m, best_s, best_i = m, s, i
    if best_i is None:
        raise RuntimeError("No dropoff")
    return pts[best_i], best_m, best_s, best_i


def build_match_light(driver: AgentState, walker: AgentState) -> MatchLight:
    pickup, pick_m, pick_s, pi = find_pickup_light(driver, walker.get_pos())
    dropoff, drop_m, drop_s, di = find_dropoff_light(driver, walker.route.dest, pi)
    if di <= pi:
        raise RuntimeError("Dropoff before pickup")

    return MatchLight(
        pickup=pickup, dropoff=dropoff,
        pickup_index=pi, dropoff_index=di,
        pick_walk_dist_m=pick_m, drop_walk_dist_m=drop_m,
        pick_walk_s=pick_s, drop_walk_s=drop_s,
    )


def finalize_match(driver_agent: AgentState, walker_agent: AgentState, ml: MatchLight) -> Match:
    """Expensive part, only for the chosen driver: full walking routes + all numbers."""
    driver = driver_agent.route

    walker_pos = walker_agent.get_pos()
    walker_dest = walker_agent.route.dest

    # baseline remaining walk from now -> dest (saving must be based on current state)
    baseline_walk = build_walker_route_full(walker_pos, walker_dest)

    walk_to = build_walker_route_full(walker_pos, ml.pickup)
    if not is_within_dist(walk_to.dest, ml.pickup, config.MAX_SNAP_DIST_M):
        raise RuntimeError("Pickup endpoint too far")

    walk_from = build_walker_route_full(ml.dropoff, walker_dest)
    if not is_within_dist(walk_from.start, ml.dropoff, config.MAX_SNAP_DIST_M):
        raise RuntimeError("Dropoff start too far")

    total_walk_m = ml.pick_walk_dist_m + ml.drop_walk_dist_m
    total_walk_s = ml.pick_walk_s + ml.drop_walk_s

    pi, di = ml.pickup_index, ml.dropoff_index
    ride_m = driver.cum_dist_m[di] - driver.cum_dist_m[pi]
    ride_s = driver.cum_time_s[di] - driver.cum_time_s[pi]

    # driver ETA from NOW (driver may already be mid-route)
    t0 = driver.cum_time_s[driver_agent.idx]
    pickup_eta_from_now = driver.cum_time_s[pi] - t0
    dropoff_eta_from_now = driver.cum_time_s[di] - t0

    return Match(
        driver=driver,
        walker=baseline_walk,
        walk_route_to_pickup=walk_to,
        walk_route_from_dropoff=walk_from,
        pickup=ml.pickup, dropoff=ml.dropoff,
        pickup_index=pi, dropoff_index=di,
        pick_walk_dist_meters=ml.pick_walk_dist_m,
        drop_walk_dist_meters=ml.drop_walk_dist_m,
        total_walk_dist_meters=total_walk_m,
        pick_walk_duration_seconds=ml.pick_walk_s,
        drop_walk_duration_seconds=ml.drop_walk_s,
        total_walk_duration_seconds=total_walk_s,
        ride_dist_meters=ride_m,
        ride_duration_seconds=ride_s,
        saving_dist_meters=baseline_walk.dist - total_walk_m,
        saving_duration_seconds=baseline_walk.duration - total_walk_s,
        driver_pickup_eta_s=pickup_eta_from_now,
        driver_dropoff_eta_s=dropoff_eta_from_now,
    )


# ---------------------------------------------------------- best driver

def best_match_(drivers: List[AgentState], walker_agent: AgentState,
                min_saving_m: float = config.MIN_SAVING_M
                ) -> Tuple[Optional[Match], Optional[AgentState]]:
    """Driver with the earliest arrival of the walker at their destination.
    Returns (match, driver) or (None, None)."""
    best_light = None
    best_driver = None
    best_arrival = float("inf")

    walker_pos = walker_agent.get_pos()
    walker_dest = walker_agent.route.dest

    # baseline remaining walk distance/time from NOW -> dest
    base_m, base_s = walk_fast(walker_pos, walker_dest)

    for d_agent in drivers:
        try:
            ml = build_match_light(d_agent, walker_agent)

            # ETA from NOW
            t0 = d_agent.route.cum_time_s[d_agent.idx]
            pickup_eta = d_agent.route.cum_time_s[ml.pickup_index] - t0
            dropoff_eta = d_agent.route.cum_time_s[ml.dropoff_index] - t0

            # sanity: pickup must be reachable in future
            if pickup_eta < 0 or dropoff_eta < 0:
                continue

            # saving check (from current situation)
            saving_m = base_m - (ml.pick_walk_dist_m + ml.drop_walk_dist_m)
            if saving_m < min_saving_m:
                continue

            # walker must arrive before driver at pickup
            if ml.pick_walk_s > pickup_eta:
                continue

            arrival = dropoff_eta + ml.drop_walk_s
            if arrival < best_arrival:
                best_arrival = arrival
                best_light = ml
                best_driver = d_agent

        except RuntimeError:
            continue

    if best_driver is None:
        return None, None

    try:
        return finalize_match(best_driver, walker_agent, best_light), best_driver
    except RuntimeError:
        return None, None


# ------------------------------------------------ matching agents into sims

def create_matches(driver_agent_list: List[AgentState],
                   walker_agent_list: List[AgentState],
                   now_t: float,
                   min_saving_m: float = config.MIN_SAVING_M
                   ) -> Tuple[List[MatchSimulation], List[AgentState], List[AgentState]]:
    """Greedy: each walker in turn takes its best free driver.
    Matched agents are REMOVED from the given lists (in place)."""
    match_simulation_list = []
    drivers = driver_agent_list.copy()
    for walker_agent in walker_agent_list.copy():
        match, driver_agent = best_match_(drivers, walker_agent, min_saving_m)
        if match is None:
            continue
        driver_agent.assigned = True
        walker_agent.assigned = True
        drivers.remove(driver_agent)
        driver_agent_list.remove(driver_agent)
        walker_agent_list.remove(walker_agent)

        match_simulation_list.append(MatchSimulation(
            match=match,
            driver_agent=driver_agent,
            walker_agent=walker_agent,
            walk_to_pickup_agent=create_agent(match.walk_route_to_pickup, offset=now_t),
            walk_from_dropoff_agent=create_agent(match.walk_route_from_dropoff,
                                                 offset=now_t + match.driver_dropoff_eta_s),
            creation_time_s=now_t,
        ))
    return match_simulation_list, driver_agent_list, walker_agent_list


def process_new_agent(kind: str,
                      new_agent: AgentState,
                      t: float,
                      matches_sim_list: list,
                      driver_agent_list: list,
                      walker_agent_list: list,
                      agent_id_to_request_id: dict,
                      handler,
                      req_id: str,
                      min_saving_m: float) -> dict:
    """Try to match a newly created agent against the waiting ones."""
    if kind == "driver":
        matches_new, _, _ = create_matches(
            [new_agent], walker_agent_list, now_t=t, min_saving_m=min_saving_m)
        waiting_list = driver_agent_list
    elif kind == "walker":
        matches_new, _, _ = create_matches(
            driver_agent_list, [new_agent], now_t=t, min_saving_m=min_saving_m)
        waiting_list = walker_agent_list
    else:
        raise ValueError(f"Unknown kind: {kind}")

    matches_sim_list.extend(matches_new)
    agent_id_to_request_id[new_agent.agent_id] = req_id

    if not matches_new:
        waiting_list.append(new_agent)
        return {"status": Status.NOT_MATCHED, "req_id": req_id, "agent_id": new_agent.agent_id}

    ms = matches_new[0]
    partner = ms.walker_agent if kind == "driver" else ms.driver_agent
    return {
        "status": Status.MATCHED,
        "req_id": req_id,
        "agent_id": new_agent.agent_id,
        "match_id": ms.match_id,
        "partner_req_id": agent_id_to_request_id.get(partner.agent_id),
        "partner_agent_id": partner.agent_id,
        "match_sim": ms,
    }
