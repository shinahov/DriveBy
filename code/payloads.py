"""JSON messages sent to the browser. The frontend (web/*.js) depends on these keys."""
from typing import List, Optional

from MatchSimulation import MatchSimulation, Phase


def build_routes_payload(sims: List[MatchSimulation], version: float) -> dict:
    routes = []
    for sim in sims:
        if sim.phase == Phase.DONE:
            continue
        m = sim.match
        routes.append({
            "match_id": sim.match_id,
            "driver_route": {"geometry_latlon": sim.driver_agent.route.geometry_latlon},
            "walk_to_pickup": {"geometry_latlon": m.walk_route_to_pickup.geometry_latlon},
            "walk_from_dropoff": {"geometry_latlon": m.walk_route_from_dropoff.geometry_latlon},
            "points": {"pickup": m.pickup, "dropoff": m.dropoff},
            "idx": {"pickup": m.pickup_index, "dropoff": m.dropoff_index},
        })
    return {"routes_version": version, "routes": routes}


def snapshot_all(t_s: float, sims: list, agent_id_to_request_id: Optional[dict] = None) -> dict:
    ids = agent_id_to_request_id or {}
    frames = []
    for sim in sims:
        walker_pos = sim.get_walker_pos()
        driver_pos = sim.get_driver_pos()
        frames.append({
            "sim_id": sim.match_id,
            "phase": sim.phase.name,
            "walker": {"agent_id": sim.walker_agent.agent_id,
                       "req_id": ids.get(sim.walker_agent.agent_id),
                       "lat": walker_pos[0],
                       "lon": walker_pos[1],
                       "pIdx": sim.walk_to_pickup_agent.idx,
                       "dIdx": sim.walk_from_dropoff_agent.idx},
            "driver": {"agent_id": sim.driver_agent.agent_id,
                       "req_id": ids.get(sim.driver_agent.agent_id),
                       "lat": driver_pos[0],
                       "lon": driver_pos[1],
                       "idx": sim.driver_agent.idx},
            "meta": {
                "t_driver_pickup": sim.match.driver_pickup_eta_s,
                "t_driver_dropoff": sim.match.driver_dropoff_eta_s,
            },
        })
    return {"t_s": t_s, "sims": frames}


def build_leftovers_payload(agent_list: list, include_agent_id: bool) -> List[dict]:
    out = []
    for a in agent_list:
        lat, lon = a.get_pos()
        item = {"lat": lat, "lon": lon}
        if include_agent_id:
            item["agent_id"] = a.agent_id
        out.append(item)
    return out


def build_snapshot_payload(t_s: float,
                           sims: list,
                           driver_agents: list,
                           walker_agents: list,
                           agent_id_to_request_id: Optional[dict] = None,
                           include_agent_id: bool = True) -> dict:
    data = snapshot_all(t_s, sims, agent_id_to_request_id)
    data["leftover_drivers"] = build_leftovers_payload(driver_agents, include_agent_id)
    data["leftover_walkers"] = build_leftovers_payload(walker_agents, include_agent_id)
    return data
