import math

import folium
import requests
import webbrowser
from typing import List, Tuple, Optional

from DriverRoute import LatLon, DriverRoute
from WalkerRoute import WalkerRoute

OSRM_BASE = "http://localhost:5000"

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


def find_closest_dropout_point(driver: DriverRoute, walker: WalkerRoute, pickup: LatLon, k: int = 20) -> Tuple[LatLon, float]:
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
    return pts[best_i], best_d


def find_closest_pickup_point(driver: DriverRoute, walker: WalkerRoute, k: int = 30) -> Tuple[LatLon, float]:
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
    return pts[best_i], best_d


def find_pickup_and_dropoff(driver: DriverRoute, walker: WalkerRoute) -> Tuple[float, float, float, float, float, float]:
    pickup,  pick_dist = find_closest_pickup_point(driver, walker)
    dropoff, drop_dist = find_closest_dropout_point(driver, walker, pickup)

    return pickup[0], pickup[1], pick_dist, dropoff[0], dropoff[1], drop_dist


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

    geometry_latlon = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
    seg_dist = ann["distance"]
    nodes = ann.get("nodes")

    cum_dist = build_cum_dist(seg_dist)

    return geometry_latlon, seg_dist, cum_dist, nodes


start = (51.2562, 7.1508)
end = (51.2277, 6.7735)

walker_start = (51.202561, 6.780486)
walker_end = (51.219105, 6.787711)

d_geom, d_seg, d_cum, d_nodes = fetch_route(start, end, "driving")
w_geom, w_seg, w_cum, w_nodes = fetch_route(walker_start, walker_end, "walking")

driver = DriverRoute(
    start=start,
    dest=end,
    profile="driving",
    geometry_latlon=d_geom,
    seg_dist_m=d_seg,
    cum_dist_m=d_cum,
    nodes=d_nodes,
)

walker = WalkerRoute(
    start=walker_start,
    dest=walker_end,
    profile="walking",
    geometry_latlon=w_geom,
    seg_dist_m=w_seg,
    cum_dist_m=w_cum,
    nodes=w_nodes,
)

pickup_lat, pickup_lon, pick_dist, dropoff_lat, dropoff_lon, drop_dist = find_pickup_and_dropoff(driver, walker)
pickup = (pickup_lat, pickup_lon)
dropoff = (dropoff_lat, dropoff_lon)

m = folium.Map(location=start, zoom_start=12)

# markers
folium.Marker(driver.start, tooltip="Driver Start", icon=folium.Icon(color="green")).add_to(m)
folium.Marker(driver.dest, tooltip="Driver End", icon=folium.Icon(color="red")).add_to(m)
folium.Marker(walker.start, tooltip="Walker Start", icon=folium.Icon(color="blue")).add_to(m)
folium.Marker(walker.dest, tooltip="Walker End", icon=folium.Icon(color="orange")).add_to(m)

# polylines
folium.PolyLine(driver.geometry_latlon, weight=5, opacity=0.8).add_to(m)
folium.PolyLine(walker.geometry_latlon, color="red", weight=5, opacity=0.8).add_to(m)

# pickup / dropoff markers
folium.Marker(
    pickup,
    tooltip="Pickup (Driver meets Walker)",
    icon=folium.Icon(color="purple", icon="play")
).add_to(m)

folium.Marker(
    dropoff,
    tooltip="Dropoff (Driver leaves Walker)",
    icon=folium.Icon(color="black", icon="stop")
).add_to(m)



# optional: visualize walker walking to pickup and from dropoff
walker_to_pickup = fetch_route(walker.start, pickup, "walking")[0]
walker_from_dropoff = fetch_route(dropoff, walker.dest, "walking")[0]
folium.PolyLine(walker_to_pickup, color="cyan", weight=3, opacity=0.6, dash_array='5').add_to(m)
folium.PolyLine(walker_from_dropoff, color="cyan", weight=3, opacity=0.6, dash_array='5').add_to(m)


m.save("map.html")
webbrowser.open("map.html")
