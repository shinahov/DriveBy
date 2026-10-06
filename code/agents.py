"""Creating driver/walker agents from OSRM routes."""
from typing import List

from AgentState import AgentState
from geo import LatLon, random_offset
from osrm_client import fetch_route
from RouteBase import DriverRoute, RouteBase, WalkerRoute


def create_agent(route: RouteBase, offset: float) -> AgentState:
    return AgentState(route=route, pos=route.start, start_offset_s=offset)


def _route_kwargs(start: LatLon, dest: LatLon, r: dict, profile: str) -> dict:
    return dict(
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


def create_driver_agent(start: LatLon, dest: LatLon, offset: float) -> AgentState:
    r = fetch_route(start, dest, "driving")
    return create_agent(DriverRoute(**_route_kwargs(start, dest, r, "driving")), offset)


def create_walker_agent(start: LatLon, dest: LatLon, offset: float) -> AgentState:
    r = fetch_route(start, dest, "walking")
    return create_agent(WalkerRoute(**_route_kwargs(start, dest, r, "walking")), offset)


def create_drivers(start: LatLon, dest: LatLon, radius_m: float, count: int) -> List[AgentState]:
    """Random drivers around start/dest (for simulated test traffic)."""
    return [create_driver_agent(random_offset(start, radius_m),
                                random_offset(dest, radius_m), offset=0.0)
            for _ in range(count)]


def create_walkers(center_start: LatLon, center_dest: LatLon,
                   radius_m: float, count: int) -> List[AgentState]:
    """Random walkers around start/dest (for simulated test traffic)."""
    return [create_walker_agent(random_offset(center_start, radius_m),
                                random_offset(center_dest, radius_m), offset=0.0)
            for _ in range(count)]


def handle_req(req: dict, offset: float):
    """Turn a create_request from the browser into an agent.
    Returns (request_id, agent, kind)."""
    req_id = req.get("request_id", "unknown")
    payload = req.get("payload", {})

    start = (payload["start"]["lat"], payload["start"]["lon"])
    dest = (payload["dest"]["lat"], payload["dest"]["lon"])
    agent = None
    if payload["type"] == "driver":
        agent = create_driver_agent(start, dest, offset=offset)
    elif payload["type"] == "walker":
        agent = create_walker_agent(start, dest, offset=offset)
    return req_id, agent, payload["type"]
