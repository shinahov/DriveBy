import math
import random
import folium
import requests
import webbrowser
from typing import List, Tuple, Optional

from DriverRoute import LatLon
from WalkerRoute import WalkerRoute
from DriverRoute import DriverRoute
from Match import Match

OSRM_BASE = "http://localhost:5000"


def valid_ride(walker_direct_m: float, total_walk_m: float, min_saving_m: float = 800) -> bool:
    return (walker_direct_m - total_walk_m) >= min_saving_m



def best_driver(drivers: List[DriverRoute], walker: WalkerRoute) -> DriverRoute | None:
    global pick_dist, drop_dist, total_walk
    best_driver = None
    best_total_walk = float("inf")
    for driver in drivers:
        try:
            _, _, pick_dist, _, _, drop_dist = find_pickup_and_dropoff(driver, walker)
            total_walk = pick_dist + drop_dist
            if total_walk < best_total_walk:
                best_total_walk = total_walk
                best_driver = driver
        except RuntimeError:
            continue
    if best_driver is None:
        raise RuntimeError("No suitable driver found")
    if valid_ride(walker.dist, total_walk):
        return best_driver
    else:
        return None

def random_offset(point:LatLon , radius: float) -> Tuple[float, float]:
    lat, lon = point
    grad = 111320.0  # meters per degree latitude
    # Convert radius from meters to degrees
    dlat = random.uniform(-radius, radius) / grad
    dlon = random.uniform(-radius, radius) / (grad * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon
def create_dirivers(start: LatLon, dest:LatLon, radius: float, cont:int) -> List[DriverRoute]:
    drivers = []
    for _ in range(cont):
        driver_start = random_offset(start, radius)
        driver_end = random_offset(dest, radius)
        d_geom, d_seg, d_cum, d_nodes, dist, dur = fetch_route(driver_start, driver_end, "driving")
        driver = DriverRoute(
            start=driver_start,
            dest=driver_end,
            dist= dist,
            duration= dur,
            profile="driving",
            geometry_latlon=d_geom,
            seg_dist_m=d_seg,
            cum_dist_m=d_cum,
            nodes=d_nodes,
        )
        drivers.append(driver)
    return drivers

def haversine_m(a: LatLon, b: LatLon) -> float:
    R = 6371000.0
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    x = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(x))

def _topk_by_haversine(points: List[LatLon], target: LatLon, k: int) -> List[int]:
    idx_d = [(i, haversine_m(p, target)) for i, p in enumerate(points)]
    idx_d.sort(key=lambda t: t[1])
    return [i for i, _ in idx_d[:min(k, len(idx_d))]]

def _closest_point_index(points: List[LatLon], target: LatLon) -> int:
    best_i = 0
    best_d = float("inf")
    for i, p in enumerate(points):
        d = haversine_m(p, target)
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def compute_walking_distance(a: LatLon, b: LatLon) -> float:
    # Walking distance in meters using OSRM (profile='walking').
    a_lat, a_lon = a
    b_lat, b_lon = b
    coords = f"{a_lon},{a_lat};{b_lon},{b_lat}"
    url = f"{OSRM_BASE}/route/v1/walking/{coords}?overview=false"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok":
        raise RuntimeError(data)
    route = data["routes"][0]
    return route["distance"]


def find_closest_dropout_point(driver: DriverRoute, walker: WalkerRoute, pickup: LatLon, k: int = 20) -> Tuple[LatLon, float, int]:
    pts = driver.geometry_latlon

    # robust: pickup index via nearest geometry point (not equality)
    pickup_i = _closest_point_index(pts, pickup)

    # only consider points AFTER pickup
    tail = pts[pickup_i+1:]
    if not tail:
        raise RuntimeError("Pickup is at/near end of driver route")

    # candidates in tail by haversine to walker.dest
    cand_local = _topk_by_haversine(tail, walker.dest, k)
    cand_idx = [pickup_i + 1 + j for j in cand_local]

    best_i = None
    best_d = float("inf")
    for i in cand_idx:
        d = compute_walking_distance(pts[i], walker.dest)
        if d < best_d:
            best_d = d
            best_i = i

    if best_i is None:
        raise RuntimeError("No dropout point found")
    return pts[best_i], best_d, best_i


def find_closest_pickup_point(driver: DriverRoute, walker: WalkerRoute, k: int = 30) -> Tuple[LatLon, float, int]:
    pts = driver.geometry_latlon
    cand_idx = _topk_by_haversine(pts, walker.start, k)

    best_i = None
    best_d = float("inf")
    for i in cand_idx:
        d = compute_walking_distance(pts[i], walker.start)
        if d < best_d:
            best_d = d
            best_i = i

    if best_i is None:
        raise RuntimeError("No pickup point found")
    return pts[best_i], best_d, best_i


def find_pickup_and_dropoff(driver, walker):
    pickup, pick_d, pi = find_closest_pickup_point(driver, walker)
    dropoff, drop_d, di = find_closest_dropout_point(driver, walker, pickup)
    if di <= pi:
        raise RuntimeError("Dropoff before pickup")
    return pickup, pick_d, pi, dropoff, drop_d, di



def build_cum_dist(seg_dist: List[float]) -> List[float]:
    cum = [0.0]
    total = 0.0
    for d in seg_dist:
        total += d
        cum.append(total)
    return cum


def fetch_route(start: LatLon, dest: LatLon, profile: str):
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
    total_dist_m = route["distance"]  # oder leg["distance"]
    total_time_s = route["duration"]  # optional
    geometry_latlon = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
    seg_dist = ann["distance"]
    nodes = ann.get("nodes")

    cum_dist = build_cum_dist(seg_dist)

    return geometry_latlon, seg_dist, cum_dist, nodes, total_dist_m, total_time_s


start = (51.2562, 7.1508)
end = (51.2277, 6.7735)

walker_start = (51.202561, 6.780486)
walker_end = (51.219105, 6.787711)

d_geom, d_seg, d_cum, d_nodes, d_dist, d_dur = fetch_route(start, end, "driving")
w_geom, w_seg, w_cum, w_nodes, w_dist, w_dur = fetch_route(walker_start, walker_end, "walking")

driver = DriverRoute(
    start=start,
    dest=end,
    dist= d_dist,
    duration=d_dur,
    profile="driving",
    geometry_latlon=d_geom,
    seg_dist_m=d_seg,
    cum_dist_m=d_cum,
    nodes=d_nodes,
)

walker = WalkerRoute(
    start=walker_start,
    dest=walker_end,
    dist= w_dist,
    duration=w_dur,
    profile="walking",
    geometry_latlon=w_geom,
    seg_dist_m=w_seg,
    cum_dist_m=w_cum,
    nodes=w_nodes,
)

drivers = create_dirivers(start, end, radius=500, cont=10)
best = best_driver(drivers, walker)
pickup, pick_d, pi, dropoff, drop_d, di = find_pickup_and_dropoff(best, walker)

if best == None:
    print("none")
else:
    match = Match(
        driver=best,
        walker=walker,
        pickup=pickup,
        dropoff=dropoff,
        pick_walk_m=pick_d,
        drop_walk_m=drop_d,
        total_walk_m=pick_d+drop_d,
        saving_m=walker.dist-pick_d+drop_d
    )

m = folium.Map(location=start, zoom_start=12)

folium.Marker(walker.start, popup="Walker Start", icon=folium.Icon(color='blue')).add_to(m)
folium.Marker(walker.dest, popup="Walker End", icon=folium.Icon(color='orange')).add_to(m)
folium.PolyLine(walker.geometry_latlon, color="green", weight=5, opacity=0.8, tooltip="Walker Route").add_to(m)

for i, d in enumerate(drivers):
    folium.PolyLine(d.geometry_latlon, color="red", weight=3, opacity=1, tooltip=f"Driver {i} Route").add_to(m)
    folium.Marker(d.start, tooltip=f"Driver {i} Start", icon=folium.Icon(color="lightgreen")).add_to(m)
    folium.Marker(d.dest,  tooltip=f"Driver {i} End",   icon=folium.Icon(color="orange")).add_to(m)

folium.PolyLine(match.driver.geometry_latlon, color="blue", weight=5, opacity=0.8, tooltip="Best Driver Route").add_to(m)
folium.Marker(match.driver.start, tooltip="Best Driver Start", icon=folium.Icon(color="green")).add_to(m)
folium.Marker(match.driver.dest,  tooltip="Best Driver End",   icon=folium.Icon(color="red")).add_to(m)



folium.Marker(
    match.pickup,
    tooltip=f"Pickup (walk {pick_d:.0f} m)",
    icon=folium.Icon(color="purple", icon="play")
).add_to(m)

folium.Marker(
    match.dropoff,
    tooltip=f"Dropoff (walk {drop_d:.0f} m)",
    icon=folium.Icon(color="black", icon="stop")
).add_to(m)

walker_to_pickup = fetch_route(match.walker.start, match.pickup, "walking")[0]
walker_from_dropoff = fetch_route(match.dropoff, match.walker.dest, "walking")[0]
folium.PolyLine(walker_to_pickup, color="cyan", weight=3, opacity=0.7, dash_array="6").add_to(m)
folium.PolyLine(walker_from_dropoff, color="cyan", weight=3, opacity=0.7, dash_array="6").add_to(m)

m.save("map.html")
webbrowser.open("map.html")