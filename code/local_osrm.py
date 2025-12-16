import math
import random
import time

import folium
import requests
import webbrowser
from typing import List, Tuple, Optional, Dict, Any
from functools import lru_cache

from DriverRoute import LatLon, DriverRoute
from WalkerRoute import WalkerRoute
from Match import Match
from AgentState import AgentState
from MatchSimulation import MatchSimulation
from realtime_runner import *

OSRM_BASE = "http://localhost:5000"


# -------------------------
# small utils
# -------------------------
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

def fetch_route(start: LatLon,
                dest: LatLon,
                profile: str) -> Dict[str, Any]:
    a_lat, a_lon = start
    b_lat, b_lon = dest

    coords = f"{a_lon},{a_lat};{b_lon},{b_lat}"
    url = (
        f"{OSRM_BASE}/route/v1/{profile}/{coords}"
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


@lru_cache(maxsize=50_000)
def route_cached(
    a_lat: float, a_lon: float,
    b_lat: float, b_lon: float,
    profile: str
) -> Dict[str, Any]:
    # cache key is primitive floats + profile
    return fetch_route((a_lat, a_lon), (b_lat, b_lon), profile)


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


def create_drivers(start: LatLon,
                   dest: LatLon,
                   radius_m: float,
                   count: int) -> List[DriverRoute]:
    drivers = []
    driver_agents= []
    for _ in range(count):
        s = random_offset(start, radius_m)
        e = random_offset(dest, radius_m)

        r = fetch_route(s, e, "driving")
        driver = DriverRoute(
                start=s,
                dest=e,
                dist=r["total_dist"],
                duration=r["total_time"],
                duration_list=r["seg_time"],
                cum_time_s=r["cum_time"],
                profile="driving",
                geometry_latlon=r["geometry"],
                seg_dist_m=r["seg_dist"],
                cum_dist_m=r["cum_dist"],
                nodes=r["nodes"],
            )
        drivers.append(
            driver
        )
        driver_agents.append(
            AgentState(
                route=driver,
                pos=driver.start
            ))
    return drivers, driver_agents


# -------------------------
# pickup / dropoff selection
# -------------------------
def find_pickup(driver: DriverRoute,
                walker: WalkerRoute,
                k: int = 15) -> (
        Tuple)[LatLon, float, float, int]:
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
                 k: int = 10) -> (
        tuple)[Any, float, float, float]:
    pts = driver.geometry_latlon
    tail = pts[pickup_i + 1 :]
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


def build_match(driver: DriverRoute, walker: WalkerRoute) -> Match:
    pickup, pick_m, pick_s, pi = find_pickup(driver, walker)
    dropoff, drop_m, drop_s, di = find_dropoff(driver, walker, pickup, pi)
    if di <= pi:
        raise RuntimeError("Dropoff before pickup")

    total_walk_m = pick_m + drop_m
    total_walk_s = pick_s + drop_s

    ride_m = driver.cum_dist_m[di] - driver.cum_dist_m[pi]
    ride_s = driver.cum_time_s[di] - driver.cum_time_s[pi]

    saving_m = walker.dist - total_walk_m
    saving_s = walker.duration - total_walk_s

    walk_route_to_pickup = build_walker_route(walker.start, pickup, "walking")
    walk_route_from_dropoff = build_walker_route(dropoff, walker.dest, "walking")

    return Match(
        driver=driver,
        walker=walker,
        walk_route_to_pickup=walk_route_to_pickup,
        walk_route_from_dropoff=walk_route_from_dropoff,
        pickup=pickup,
        dropoff=dropoff,
        pickup_index=pi,
        dropoff_index=di,
        pick_walk_dist_meters=pick_m,
        drop_walk_dist_meters=drop_m,
        total_walk_dist_meters=total_walk_m,
        pick_walk_duration_seconds=pick_s,
        drop_walk_duration_seconds=drop_s,
        total_walk_duration_seconds=total_walk_s,
        ride_dist_meters=ride_m,
        ride_duration_seconds=ride_s,
        saving_dist_meters=saving_m,
        saving_duration_seconds=saving_s,
        driver_pickup_eta_s=driver.cum_time_s[pi],
        driver_dropoff_eta_s=driver.cum_time_s[di],
    )


def valid_match(match: Match, min_saving_m: float = 800.0) -> bool:
    return match.saving_dist_meters >= min_saving_m


def best_match(drivers: List[DriverRoute], walker: WalkerRoute, min_saving_m: float = 800.0) -> Optional[Match]:
    best: Optional[Match] = None
    best_total_walk = float("inf")

    for d in drivers:
        try:
            m = build_match(d, walker)
            if not valid_match(m, min_saving_m=min_saving_m):
                continue
            if m.total_walk_dist_meters < best_total_walk:
                best_total_walk = m.total_walk_dist_meters
                best = m
        except RuntimeError:
            continue

    return best


# -------------------------
# demo / map (OBSOLET)
# -------------------------
def draw_map(drivers: List[DriverRoute], match: Optional[Match], walker: WalkerRoute, center: LatLon) -> None:
    m = folium.Map(location=center, zoom_start=12)

    folium.Marker(walker.start, popup="Walker Start", icon=folium.Icon(color="blue")).add_to(m)
    folium.Marker(walker.dest, popup="Walker End", icon=folium.Icon(color="orange")).add_to(m)
    folium.PolyLine(walker.geometry_latlon, color="green", weight=5, opacity=0.8, tooltip="Walker Route").add_to(m)

    for i, d in enumerate(drivers):
        folium.PolyLine(d.geometry_latlon, color="red", weight=3, opacity=1, tooltip=f"Driver {i} Route").add_to(m)

    if match is not None:
        folium.PolyLine(match.driver.geometry_latlon, color="blue", weight=5, opacity=0.8, tooltip="Best Driver Route").add_to(m)

        folium.Marker(match.pickup, tooltip=f"Pickup (walk {match.pick_walk_dist_meters:.0f} m)", icon=folium.Icon(color="purple")).add_to(m)
        folium.Marker(match.dropoff, tooltip=f"Dropoff (walk {match.drop_walk_dist_meters:.0f} m)", icon=folium.Icon(color="black")).add_to(m)

        # walking lines for visualization (use cached routes)
        wtp = route_cached(walker.start[0], walker.start[1], match.pickup[0], match.pickup[1], "walking")["geometry"]
        wfd = route_cached(match.dropoff[0], match.dropoff[1], walker.dest[0], walker.dest[1], "walking")["geometry"]
        folium.PolyLine(wtp, color="cyan", weight=3, opacity=0.7, dash_array="6").add_to(m)
        folium.PolyLine(wfd, color="cyan", weight=3, opacity=0.7, dash_array="6").add_to(m)

    m.save("map.html")
    webbrowser.open("map.html")


# -------------------------
# run
# -------------------------
start = (51.2562, 7.1508)
end = (51.2277, 6.7735)
walker_start = (51.202561, 6.780486)
walker_end = (51.219105, 6.787711)

# walker route once
wr = fetch_route(walker_start, walker_end, "walking")
walker = WalkerRoute(
    start=walker_start,
    dest=walker_end,
    dist=wr["total_dist"],
    duration=wr["total_time"],
    duration_list=wr["seg_time"],
    cum_time_s=wr["cum_time"],
    profile="walking",
    geometry_latlon=wr["geometry"],
    seg_dist_m=wr["seg_dist"],
    cum_dist_m=wr["cum_dist"],
    nodes=wr["nodes"],
)
walker_agent = AgentState(
    route=walker,
    pos=walker.start
)

drivers, driver_agents = create_drivers(start, end, radius_m=500, count=10)
match = best_match(drivers, walker, min_saving_m=800)

if match is None:
    print("no match")
else:
    print("saving_m:", match.saving_dist_meters, "ride_m:", match.ride_dist_meters, "walk_m:", match.total_walk_dist_meters)

#draw_map(drivers, match, walker, center=start)

all_agents: list[tuple[str, AgentState]] = []


for i, a in enumerate(driver_agents):
    all_agents.append((f"Driver {i}", a))


best_driver_agent = None
for agent in driver_agents:
    if agent.route is match.driver:
        best_driver_agent = agent
        break

if best_driver_agent is None:
    raise RuntimeError("Matched driver agent not found")


start_server(8000)
webbrowser.open("http://127.0.0.1:8000/map.html")

sim = MatchSimulation(
    match=match,
    driver_agent=best_driver_agent,
    walk_to_pickup_agent=AgentState(
        route=match.walk_route_to_pickup,
        pos=match.walk_route_to_pickup.start
    ),
    walk_from_dropoff_agent=AgentState(
        route=match.walk_route_from_dropoff,
        pos=match.walk_route_from_dropoff.start
    ),
)

t = 0.0
dt = 0.2

while True:
    for a in driver_agents:
        if a is best_driver_agent:
            continue
        a.update_position(t)

    sim.update(t)

    walker_pos = sim.get_walker_pos()
    driver_positions = [a.get_pos() for a in driver_agents]

    data = {
        "t_s": t,
        "walker": {"lat": walker_pos[0], "lon": walker_pos[1]},
        "drivers": [{"lat": p[0], "lon": p[1]} for p in driver_positions],
    }

    write_positions_json(data)

    time.sleep(dt)
    t += dt
