import math
import random
import time
import folium
import requests
import webbrowser
from typing import List, Tuple, Optional, Dict, Any
from functools import lru_cache
from queue import Queue, Empty

from RouteBase import LatLon, DriverRoute, WalkerRoute, RouteBase
from Match import Match, MatchLight
from AgentState import AgentState
from MatchSimulation import MatchSimulation, Phase
from realtime_runner import *

OSRM_DRIVE = "http://localhost:5000"
OSRM_WALK = "http://localhost:5001"

SESSION = requests.Session()


def q(x: float, p: int = 5) -> float:  # 5 - 1m
    return round(x, p)


def cum_array(values: List[float]) -> List[float]:
    cum = [0.0]
    s = 0.0
    for v in values:
        s += v
        cum.append(s)
    return cum


def haversine_m(a: LatLon, b: LatLon) -> float:
    R = 6371000.0
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    x = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def topk_by_haversine(points: List[LatLon], target: LatLon, k: int) -> list[float]:
    idx_d = [(i, haversine_m(p, target)) for i, p in enumerate(points)]
    idx_d.sort(key=lambda t: t[1])
    return [i for i, _ in idx_d[:min(k, len(idx_d))]]


def closest_point_index(points: List[LatLon], target: LatLon) -> int:
    best_i = 0
    best_d = float("inf")
    for i, p in enumerate(points):
        d = haversine_m(p, target)
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


# -------------------------
# OSRM route fetch + cache
# -------------------------

def build_walker_route(start: LatLon, dest: LatLon, profile: str = "walking") -> WalkerRoute:
    r = fetch_route(start, dest, profile)

    return WalkerRoute(
        start=start,
        dest=dest,
        dist=r["total_dist"],
        duration=r["total_time"],
        duration_list=r["seg_time"],
        cum_time_s=r["cum_time"],
        profile=profile,
        geometry_latlon=r["geometry"],
        seg_dist_m=r["seg_dist"],
        cum_dist_m=r["cum_dist"],
        nodes=r["nodes"],
    )


def fetch_drive_route(start: LatLon, dest: LatLon):
    return fetch_route(start, dest, "driving")


def fetch_walk_route(start: LatLon, dest: LatLon):
    return fetch_route(start, dest, "walking")


def fetch_route_fast(start: LatLon, dest: LatLon, profile: str):
    base = OSRM_WALK if profile == "walking" else OSRM_DRIVE
    a_lat, a_lon = start
    b_lat, b_lon = dest
    coords = f"{a_lon},{a_lat};{b_lon},{b_lat}"
    url = f"{base}/route/v1/{profile}/{coords}?overview=false&steps=false"

    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok":
        raise RuntimeError(data)
    route = data["routes"][0]
    return route["distance"], route["duration"]


def build_walker_route_full(start: LatLon, dest: LatLon) -> WalkerRoute:
    r = fetch_route(start, dest, "walking")
    return WalkerRoute(
        start=start, dest=dest,
        dist=r["total_dist"], duration=r["total_time"],
        duration_list=r["seg_time"], cum_time_s=r["cum_time"],
        profile="walking", geometry_latlon=r["geometry"],
        seg_dist_m=r["seg_dist"], cum_dist_m=r["cum_dist"],
        nodes=r["nodes"],
    )


def fetch_route(start: LatLon, dest: LatLon, profile: str):
    if profile == "walking":
        base = OSRM_WALK
    elif profile == "driving":
        base = OSRM_DRIVE
    else:
        raise ValueError(f"Unknown profile: {profile}")

    a_lat, a_lon = start
    b_lat, b_lon = dest

    coords = f"{a_lon},{a_lat};{b_lon},{b_lat}"
    print(coords)
    url = (
        f"{base}/route/v1/{profile}/{coords}"
        "?overview=full&geometries=geojson&annotations=true&steps=false"
    )

    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok":
        raise RuntimeError(data)

    route = data["routes"][0]
    leg = route["legs"][0]
    ann = leg["annotation"]

    geometry_latlon = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
    seg_dist = ann["distance"]
    seg_time = ann["duration"]
    nodes = ann.get("nodes")

    return {
        "geometry": geometry_latlon,
        "seg_dist": seg_dist,
        "cum_dist": cum_array(seg_dist),
        "seg_time": seg_time,
        "cum_time": cum_array(seg_time),
        "nodes": nodes,
        "total_dist": route["distance"],
        "total_time": route["duration"],
    }


@lru_cache(maxsize=200_000)
def route_fast_cached(a_lat: float, a_lon: float, b_lat: float, b_lon: float, profile: str):
    base = OSRM_WALK if profile == "walking" else OSRM_DRIVE
    coords = f"{a_lon},{a_lat};{b_lon},{b_lat}"
    url = f"{base}/route/v1/{profile}/{coords}?overview=false&steps=false"

    r = SESSION.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok":
        raise RuntimeError(data)
    route = data["routes"][0]
    return route["distance"], route["duration"]


@lru_cache(maxsize=50_000)
def route_cached(
        a_lat: float, a_lon: float,
        b_lat: float, b_lon: float,
        profile: str
) -> Dict[str, Any]:
    # cache key is primitive floats + profile
    return fetch_route((a_lat, a_lon), (b_lat, b_lon), profile)


def walk_fast(a: LatLon, b: LatLon) -> tuple[float, float]:
    return route_fast_cached(q(a[0]), q(a[1]), q(b[0]), q(b[1]), "walking")


def walk_dist(a: LatLon, b: LatLon) -> float:
    return route_cached(a[0], a[1], b[0], b[1], "walking")["total_dist"]


def walk_time(a: LatLon, b: LatLon) -> float:
    return route_cached(a[0], a[1], b[0], b[1], "walking")["total_time"]


# -------------------------
# drivers generation
# -------------------------
def random_offset(point: LatLon, radius_m: float) -> LatLon:
    lat, lon = point
    grad = 111320.0
    dlat = random.uniform(-radius_m, radius_m) / grad
    dlon = random.uniform(-radius_m, radius_m) / (grad * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


def create_driver_agent(start: LatLon, dest: LatLon, offset: float) -> AgentState:
    r = fetch_route(start, dest, "driving")
    route = DriverRoute(
        start=start,
        dest=dest,
        dist=r["total_dist"],
        duration=r["total_time"],
        duration_list=r["seg_time"],
        cum_time_s=r["cum_time"],
        profile="walking",
        geometry_latlon=r["geometry"],
        seg_dist_m=r["seg_dist"],
        cum_dist_m=r["cum_dist"],
        nodes=r["nodes"],
    )
    driver_agent = AgentState(
        route=route,
        pos=route.start,
        start_offset_s=offset
    )
    return driver_agent


def create_drivers(start: LatLon,
                   dest: LatLon,
                   radius_m: float,
                   count: int) -> List[AgentState]:
    driver_agents = []
    for _ in range(count):
        s = random_offset(start, radius_m)
        e = random_offset(dest, radius_m)
        driver_agents.append(
            create_driver_agent(start=s, dest=e, offset=0.0
                                ))
    return driver_agents


def create_walker_agent(start: LatLon, dest: LatLon, offset: float) -> AgentState:
    r = fetch_route(start, dest, "walking")
    route = WalkerRoute(
        start=start,
        dest=dest,
        dist=r["total_dist"],
        duration=r["total_time"],
        duration_list=r["seg_time"],
        cum_time_s=r["cum_time"],
        profile="walking",
        geometry_latlon=r["geometry"],
        seg_dist_m=r["seg_dist"],
        cum_dist_m=r["cum_dist"],
        nodes=r["nodes"],
    )
    walker_agent = AgentState(
        route=route,
        pos=route.start,
        start_offset_s=offset
    )
    return walker_agent


def create_walkers(center_start: LatLon,
                   center_dest: LatLon,
                   radius_m: float,
                   count: int) -> List[AgentState]:
    walker_agents: List[AgentState] = []
    for _ in range(count):
        s = random_offset(center_start, radius_m)
        e = random_offset(center_dest, radius_m)
        walker_agents.append(create_walker_agent(start=s, dest=e, offset=0.0))
    return walker_agents


# pickup / dropoff selection


def find_pickup_light(driver: RouteBase, walker: RouteBase, k: int = 15):
    pts = driver.geometry_latlon
    cand_idx = topk_by_haversine(pts, walker.start, k)

    best_i = None
    best_m = float("inf")
    best_s = float("inf")
    for i in cand_idx:
        m, s = walk_fast(walker.start, pts[i])  # start -> pickup
        if m < best_m:
            best_m, best_s, best_i = m, s, i
    if best_i is None:
        raise RuntimeError("No pickup point found")
    return pts[best_i], best_m, best_s, best_i


def find_dropoff_light(driver: DriverRoute, walker: WalkerRoute, pickup_i: int, k: int = 10):
    pts = driver.geometry_latlon
    tail = pts[pickup_i + 1:]
    if not tail:
        raise RuntimeError("Pickup at end")

    cand_local = topk_by_haversine(tail, walker.dest, k)
    cand_idx = [pickup_i + 1 + j for j in cand_local]

    best_i = None
    best_m = float("inf")
    best_s = float("inf")
    for i in cand_idx:
        m, s = walk_fast(pts[i], walker.dest)  # dropoff -> dest
        if m < best_m:
            best_m, best_s, best_i = m, s, i
    if best_i is None:
        raise RuntimeError("No dropoff")
    return pts[best_i], best_m, best_s, best_i


def find_pickup(driver: RouteBase,
                walker: RouteBase,
                k: int = 15) -> Tuple[LatLon, float, float, int]:
    pts = driver.geometry_latlon
    cand_idx = topk_by_haversine(pts, walker.start, k)

    best_i = None
    best_m = float("inf")
    best_s = float("inf")
    for i in cand_idx:
        m = walk_dist(pts[i], walker.start)
        if m < best_m:
            best_m = m
            best_s = walk_time(pts[i], walker.start)
            best_i = i

    if best_i is None:
        raise RuntimeError("No pickup point found")
    return pts[best_i], best_m, best_s, best_i


def find_dropoff(driver: DriverRoute,
                 walker: WalkerRoute,
                 pickup: LatLon,
                 pickup_i: int,
                 k: int = 10) -> Tuple[LatLon, float, float, int]:
    pts = driver.geometry_latlon
    tail = pts[pickup_i + 1:]
    if not tail:
        raise RuntimeError("Pickup is at/near end of driver route")

    cand_local = topk_by_haversine(tail, walker.dest, k)
    cand_idx = [pickup_i + 1 + j for j in cand_local]

    best_i = None
    best_m = float("inf")
    best_s = float("inf")
    for i in cand_idx:
        m = walk_dist(pts[i], walker.dest)
        if m < best_m:
            best_m = m
            best_s = walk_time(pts[i], walker.dest)
            best_i = i

    if best_i is None:
        raise RuntimeError("No dropoff point found")
    return pts[best_i], best_m, best_s, best_i


def is_within_dist(p1, p2, max_dist_m):
    return haversine_m(p1, p2) <= max_dist_m


def build_match_light(driver: DriverRoute, walker: WalkerRoute) -> MatchLight:
    pickup, pick_m, pick_s, pi = find_pickup_light(driver, walker)
    dropoff, drop_m, drop_s, di = find_dropoff_light(driver, walker, pi)
    if di <= pi:
        raise RuntimeError("Dropoff before pickup")

    return MatchLight(
        pickup=pickup, dropoff=dropoff,
        pickup_index=pi, dropoff_index=di,
        pick_walk_dist_m=pick_m, drop_walk_dist_m=drop_m,
        pick_walk_s=pick_s, drop_walk_s=drop_s
    )


def finalize_match(driver: DriverRoute, walker: WalkerRoute, ml: MatchLight) -> Match:
    # expensive only once
    walk_to = build_walker_route_full(walker.start, ml.pickup)
    if not is_within_dist(walk_to.dest, ml.pickup, 30.0):
        raise RuntimeError("Pickup endpoint too far")

    walk_from = build_walker_route_full(ml.dropoff, walker.dest)
    if not is_within_dist(walk_from.start, ml.dropoff, 30.0):
        raise RuntimeError("Dropoff start too far")

    total_walk_m = ml.pick_walk_dist_m + ml.drop_walk_dist_m
    total_walk_s = ml.pick_walk_s + ml.drop_walk_s

    pi, di = ml.pickup_index, ml.dropoff_index
    ride_m = driver.cum_dist_m[di] - driver.cum_dist_m[pi]
    ride_s = driver.cum_time_s[di] - driver.cum_time_s[pi]

    saving_m = walker.dist - total_walk_m
    saving_s = walker.duration - total_walk_s

    return Match(
        driver=driver, walker=walker,
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
        saving_dist_meters=saving_m,
        saving_duration_seconds=saving_s,
        driver_pickup_eta_s=driver.cum_time_s[pi],
        driver_dropoff_eta_s=driver.cum_time_s[di],
    )


def valid_match(match: Match, min_saving_m: float = 800.0) -> bool:
    if match.saving_dist_meters < min_saving_m:
        return False
        # walker must arrive at pickup before driver
    if match.pick_walk_duration_seconds > match.driver_pickup_eta_s:
        return False
    return True


def best_match_(drivers: List[AgentState], walker: AgentState, min_saving_m: float = 800.0):
    best_light = None
    best_driver = None
    best_arrival = float("inf")

    for d_agent in drivers:
        try:
            ml = build_match_light(d_agent.route, walker.route)

            # quick validity check using light totals
            total_walk_s = ml.pick_walk_s + ml.drop_walk_s
            total_walk_m = ml.pick_walk_dist_m + ml.drop_walk_dist_m

            saving_m = walker.route.dist - total_walk_m
            if saving_m < min_saving_m:
                continue

            if ml.pick_walk_s > d_agent.route.cum_time_s[ml.pickup_index]:
                continue

            arrival = d_agent.route.cum_time_s[ml.dropoff_index] + ml.drop_walk_s
            if arrival < best_arrival:
                best_arrival = arrival
                best_light = ml
                best_driver = d_agent
        except RuntimeError:
            continue

    if best_driver is None:
        return None, None

    # expensive finalize only once
    try:
        m = finalize_match(best_driver.route, walker.route, best_light)
        return m, best_driver
    except RuntimeError:
        return None, None


def write_routes_json(sims: List[MatchSimulation], version: float, filename="routes.json"):
    routes = []

    for sim in sims:
        if sim.phase != Phase.DONE:
            m = sim.match
            routes.append({
                "match_id": sim.match_id,
                "driver_route": {
                    "geometry_latlon": sim.driver_agent.route.geometry_latlon,
                },
                "walk_to_pickup": {
                    "geometry_latlon": m.walk_route_to_pickup.geometry_latlon,
                },
                "walk_from_dropoff": {
                    "geometry_latlon": m.walk_route_from_dropoff.geometry_latlon,
                },
                "points": {
                    "pickup": m.pickup,
                    "dropoff": m.dropoff,
                },
                "idx": {
                    "pickup": m.pickup_index,
                    "dropoff": m.dropoff_index}
            })

    write_positions_json(
        {"routes_version": version, "routes": routes}, filename=filename)


# demo / map (OBSOLET)

def draw_map(drivers: List[DriverRoute], match: Optional[Match], walker: WalkerRoute, center: LatLon) -> None:
    m = folium.Map(location=center, zoom_start=12)

    folium.Marker(walker.start, popup="Walker Start", icon=folium.Icon(color="blue")).add_to(m)
    folium.Marker(walker.dest, popup="Walker End", icon=folium.Icon(color="orange")).add_to(m)
    folium.PolyLine(walker.geometry_latlon, color="green", weight=5, opacity=0.8, tooltip="Walker Route").add_to(m)

    for i, d in enumerate(drivers):
        folium.PolyLine(d.geometry_latlon, color="red", weight=3, opacity=1, tooltip=f"Driver {i} Route").add_to(m)

    if match is not None:
        folium.PolyLine(match.driver.geometry_latlon, color="blue", weight=5, opacity=0.8,
                        tooltip="Best Driver Route").add_to(m)

        folium.Marker(match.pickup, tooltip=f"Pickup (walk {match.pick_walk_dist_meters:.0f} m)",
                      icon=folium.Icon(color="purple")).add_to(m)
        folium.Marker(match.dropoff, tooltip=f"Dropoff (walk {match.drop_walk_dist_meters:.0f} m)",
                      icon=folium.Icon(color="black")).add_to(m)

        # walking lines for visualization (use cached routes)
        wtp = route_cached(walker.start[0], walker.start[1], match.pickup[0], match.pickup[1], "walking")["geometry"]
        wfd = route_cached(match.dropoff[0], match.dropoff[1], walker.dest[0], walker.dest[1], "walking")["geometry"]
        folium.PolyLine(wtp, color="cyan", weight=3, opacity=0.7, dash_array="6").add_to(m)
        folium.PolyLine(wfd, color="cyan", weight=3, opacity=0.7, dash_array="6").add_to(m)

    m.save("map.html")
    webbrowser.open("web/map.html")


# run

def create_agent(route: RouteBase, offset: float) -> AgentState:
    return AgentState(route=route, pos=route.start, start_offset_s=offset)


def create_matches(driver_agent_list,
                   walker_agent_list,
                   now_t: float,
                   min_saving_m=800) -> Tuple[List[MatchSimulation], List[AgentState], List[AgentState]]:
    match_simulation_list = []
    drivers = driver_agent_list.copy()
    walkers = walker_agent_list.copy()
    for walker_agent in walkers:
        match, driver_agent = best_match_(drivers, walker_agent, min_saving_m)
        if match is not None:
            driver_agent.assigned = True
            walker_agent.assigned = True
            drivers.remove(driver_agent)
            driver_agent_list.remove(driver_agent)
            walker_agent_list.remove(walker_agent)

            match_sim = MatchSimulation(
                match=match,
                driver_agent=driver_agent,
                walker_agent=walker_agent,
                walk_to_pickup_agent=create_agent(match.walk_route_to_pickup,
                                                  offset=now_t),
                walk_from_dropoff_agent=create_agent(match.walk_route_from_dropoff,
                                                     offset=now_t + match.driver_dropoff_eta_s),
                creation_time_s=now_t
            )
            match_simulation_list.append(match_sim)
    return match_simulation_list, driver_agent_list, walker_agent_list


def snapshot_all(t_s: float, sims: list):
    frames = []

    for i, sim in enumerate(sims):
        walker_pos = sim.get_walker_pos()
        driver_pos = sim.get_driver_pos()

        frames.append({
            "sim_id": sim.match_id,
            "phase": sim.phase.name,
            "walker": {"agent_id": sim.walker_agent.agent_id,
                       "lat": walker_pos[0],
                       "lon": walker_pos[1],
                       "pIdx": sim.walk_to_pickup_agent.idx,
                       "dIdx": sim.walk_from_dropoff_agent.idx},
            "driver": {"agent_id": sim.driver_agent.agent_id,
                       "lat": driver_pos[0],
                       "lon": driver_pos[1],
                       "idx": sim.driver_agent.idx},
            "meta": {
                "t_driver_pickup": sim.match.driver_pickup_eta_s,
                "t_driver_dropoff": sim.match.driver_dropoff_eta_s,
            }
        })

    return {
        "t_s": t_s,
        "sims": frames
    }


def handle_req(req, offset: float):
    id = req.get("request_id", "unknown")
    payload = req.get("payload", {})

    agent = None
    print(f"new {payload['type']} agent", payload["start"], payload["dest"])
    start = (payload["start"]["lat"], payload["start"]["lon"])
    dest = (payload["dest"]["lat"], payload["dest"]["lon"])
    if payload["type"] == "driver":
        agent = create_driver_agent(start, dest, offset=offset)
    elif payload["type"] == "walker":
        agent = create_walker_agent(start, dest, offset=offset)
    return id, agent, payload["type"]


# status update helper
def set_request_status(handler, req_id: str, status: str, kind: str,
                       agent_id: str | None = None, match_id: str | None = None) -> None:
    payload = {"status": status, "kind": kind, "agent_id": agent_id}
    if match_id is not None:
        payload["match_id"] = match_id
    handler.create_requests[req_id] = payload


# leftovers payload helper
def build_leftovers_payload(agent_list: list, include_agent_id: bool) -> list[dict]:
    out = []
    for a in agent_list:
        item = {"lat": a.get_pos()[0], "lon": a.get_pos()[1]}
        if include_agent_id:
            item["agent_id"] = a.agent_id
        out.append(item)
    return out


# full snapshot with leftovers
def build_snapshot_payload(t_s: float,
                           sims: list,
                           driver_agents: list,
                           walker_agents: list,
                           include_agent_id: bool) -> dict:
    data = snapshot_all(t_s, sims)
    data["leftover_drivers"] = build_leftovers_payload(driver_agents, include_agent_id)
    data["leftover_walkers"] = build_leftovers_payload(walker_agents, include_agent_id)
    return data


# process new agent helper
def process_new_agent(kind: str,
                      new_agent,
                      t: float,
                      matches_sim_list: list,
                      driver_agent_list: list,
                      walker_agent_list: list,
                      agent_id_to_request_id: dict,
                      handler,
                      req_id: str,
                      min_saving_m: float) -> None:
    # Mark request as created first
    set_request_status(
        handler, req_id, "created", kind, getattr(new_agent, "agent_id", None))

    if kind == "driver":
        matches_new, _, _ = create_matches(
            [new_agent], walker_agent_list, now_t=t, min_saving_m=min_saving_m)
        matches_sim_list.extend(matches_new)

        if not matches_new:
            set_request_status(
                handler, req_id, "not_matched", kind,
                getattr(new_agent, "agent_id", None))
            agent_id_to_request_id[new_agent.agent_id] = req_id
            driver_agent_list.append(new_agent)
            return

        ms = matches_new[0]
        set_request_status(
            handler, req_id, "matched", kind,
            new_agent.agent_id, ms.match_id)
        agent_id_to_request_id[new_agent.agent_id] = req_id

        partner_req_id = agent_id_to_request_id.get(ms.walker_agent.agent_id)
        if partner_req_id is not None:
            set_request_status(
                handler, partner_req_id, "matched", "walker",
                ms.walker_agent.agent_id, ms.match_id)
        return

    if kind == "walker":
        matches_new, _, _ = create_matches(
            driver_agent_list, [new_agent], now_t=t, min_saving_m=min_saving_m)
        matches_sim_list.extend(matches_new)

        if not matches_new:
            set_request_status(
                handler, req_id, "not_matched", kind,
                getattr(new_agent, "agent_id", None))
            agent_id_to_request_id[new_agent.agent_id] = req_id
            walker_agent_list.append(new_agent)
            return

        ms = matches_new[0]
        set_request_status(
            handler, req_id, "matched", kind, new_agent.agent_id, ms.match_id)
        agent_id_to_request_id[new_agent.agent_id] = req_id

        partner_req_id = agent_id_to_request_id.get(ms.driver_agent.agent_id)
        if partner_req_id is not None:
            set_request_status(
                handler, partner_req_id, "matched", "driver",
                ms.driver_agent.agent_id, ms.match_id)
        return

    raise ValueError(f"Unknown kind: {kind}")


# queue draining helper
def drain_create_queue(q: Queue) -> list:
    reqs = []
    while True:
        try:
            reqs.append(q.get_nowait())
        except Empty:
            break
    return reqs


def start():
    start_pt = (51.2562, 7.1508)
    end_pt = (51.2277, 6.7735)
    walker_start = (51.202561, 6.780486)
    walker_end = (51.219105, 6.787711)

    min_saving_m = 800.0
    agent_id_to_request_id: dict[str, str] = {}

    walker_agent_list = create_walkers(walker_start, walker_end, 300, 6)
    driver_agent_list = create_drivers(start_pt, end_pt, radius_m=1000, count=1)

    matches_sim_list, driver_agent_list, walker_agent_list = create_matches(
        driver_agent_list, walker_agent_list, now_t=0.0, min_saving_m=min_saving_m
    )

    if matches_sim_list is None:
        print("no match")
        raise SystemExit(0)

    print(len(matches_sim_list))

    my_queue = Queue()
    handler = start_server(create_q=my_queue, port=8000)

    # Write routes once
    write_routes_json(matches_sim_list, version=0)

    # Initial snapshot (force sim update at t=0)
    for sim in matches_sim_list:
        sim.update(0.0)

    data0 = build_snapshot_payload(
        t_s=0.0,
        sims=matches_sim_list,
        driver_agents=driver_agent_list,
        walker_agents=walker_agent_list,
        include_agent_id=False
    )
    write_positions_json(data0)

    webbrowser.open("http://127.0.0.1:8000/web/map.html?v=" + str(time.time()))

    t = 0.0
    while True:
        # Handle incoming create-requests
        for req in drain_create_queue(my_queue):
            req_id, new_agent, kind = handle_req(req, offset=t)
            process_new_agent(
                kind=kind,
                new_agent=new_agent,
                t=t,
                matches_sim_list=matches_sim_list,
                driver_agent_list=driver_agent_list,
                walker_agent_list=walker_agent_list,
                agent_id_to_request_id=agent_id_to_request_id,
                handler=handler,
                req_id=req_id,
                min_saving_m=min_saving_m
            )
            write_routes_json(matches_sim_list, version=t)

        # Update unmatched drivers
        for a in driver_agent_list:
            a.update_position(t)

        # Update all simulations
        for sim in matches_sim_list:
            sim.update(t)

        # Write one combined snapshot
        data = build_snapshot_payload(
            t_s=t,
            sims=matches_sim_list,
            driver_agents=driver_agent_list,
            walker_agents=walker_agent_list,
            include_agent_id=True
        )
        write_positions_json(data)

        dt = handler.speed
        t += dt
        time.sleep(0.05)
