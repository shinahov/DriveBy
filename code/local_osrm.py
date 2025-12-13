import folium
import requests
import webbrowser
from typing import List, Tuple, Optional

from DriverRoute import LatLon, DriverRoute
from WalkerRoute import WalkerRoute

OSRM_BASE = "http://localhost:5000"


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


def find_closest_dropout_point(driver: DriverRoute, walker: WalkerRoute, pickup:LatLon) -> Tuple[float, float]:
    min_dist = float('inf')
    best_point = None
    for point in reversed(driver.geometry_latlon):
        if point == pickup:
            break
        dist = compute_walking_distance(walker.dest, point)
        if dist < min_dist:
            min_dist = dist
            best_point = point
    if best_point is None:
        raise RuntimeError("No dropout point found after pickup.")
    return best_point


def find_closest_pickup_point(driver: DriverRoute, walker: WalkerRoute) -> Tuple[float, float]:
    min_dist = float("inf")
    best_point: LatLon | None = None

    for p in driver.geometry_latlon:
        d = compute_walking_distance(p, walker.start)
        if d < min_dist:
            min_dist = d
            best_point = p

    if best_point is None:
        raise RuntimeError("No pickup point found")

    return best_point


def find_pickup_and_dropoff(driver: DriverRoute, walker: WalkerRoute) -> Tuple[float, float, float, float]:
    pickup = find_closest_pickup_point(driver, walker)
    dropoff = find_closest_dropout_point(driver, walker, pickup)

    return pickup[0], pickup[1], dropoff[0], dropoff[1]


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

walker_start = (51.200066, 6.789997)
walker_end = (51.219932, 6.779193)

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

pickup = find_closest_pickup_point(driver, walker)
dropoff = find_closest_dropout_point(driver, walker, pickup)

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
folium.PolyLine([walker.start, pickup], weight=3, opacity=0.9, dash_array="8,6").add_to(m)
folium.PolyLine([dropoff, walker.dest], weight=3, opacity=0.9, dash_array="8,6").add_to(m)


m.save("map.html")
webbrowser.open("map.html")
