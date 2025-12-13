import folium
import requests
import webbrowser
from typing import List, Tuple, Optional

from DriverRoute import LatLon, DriverRoute
from WalkerRoute import WalkerRoute


def build_cum_dist(seg_dist: List[float]) -> List[float]:
    cum = [0.0]
    total = 0.0
    for d in seg_dist:
        total += d
        cum.append(total)
    return cum


OSRM_BASE = "http://localhost:5000"


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

m = folium.Map(location=start, zoom_start=12)

# markers
folium.Marker(driver.start, tooltip="Driver Start", icon=folium.Icon(color="green")).add_to(m)
folium.Marker(driver.dest, tooltip="Driver End", icon=folium.Icon(color="red")).add_to(m)
folium.Marker(walker.start, tooltip="Walker Start", icon=folium.Icon(color="blue")).add_to(m)
folium.Marker(walker.dest, tooltip="Walker End", icon=folium.Icon(color="orange")).add_to(m)

# polylines
folium.PolyLine(driver.geometry_latlon, weight=5, opacity=0.8).add_to(m)
folium.PolyLine(walker.geometry_latlon, color="red", weight=5, opacity=0.8).add_to(m)

m.save("map.html")
webbrowser.open("map.html")

