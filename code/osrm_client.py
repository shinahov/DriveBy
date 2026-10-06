"""Talks to the two OSRM servers (driving + walking)."""
from functools import lru_cache
from typing import Any, Dict

import requests

import config
from geo import LatLon, cum_array
from RouteBase import WalkerRoute

SESSION = requests.Session()


def q(x: float, p: int = 5) -> float:
    """Round a coordinate (5 decimals ~ 1 m) so the cache gets more hits."""
    return round(x, p)


def _base_url(profile: str) -> str:
    if profile == "walking":
        return config.OSRM_WALK
    if profile == "driving":
        return config.OSRM_DRIVE
    raise ValueError(f"Unknown profile: {profile}")


def fetch_route(start: LatLon, dest: LatLon, profile: str) -> Dict[str, Any]:
    """Full route with geometry and per-segment distance/time."""
    base = _base_url(profile)
    a_lat, a_lon = start
    b_lat, b_lon = dest
    coords = f"{a_lon},{a_lat};{b_lon},{b_lat}"
    url = (
        f"{base}/route/v1/{profile}/{coords}"
        "?overview=full&geometries=geojson&annotations=true&steps=false"
    )

    r = requests.get(url, timeout=config.OSRM_TIMEOUT_S)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok":
        raise RuntimeError(data)

    route = data["routes"][0]
    ann = route["legs"][0]["annotation"]
    seg_dist = ann["distance"]
    seg_time = ann["duration"]

    return {
        "geometry": [(lat, lon) for lon, lat in route["geometry"]["coordinates"]],
        "seg_dist": seg_dist,
        "cum_dist": cum_array(seg_dist),
        "seg_time": seg_time,
        "cum_time": cum_array(seg_time),
        "nodes": ann.get("nodes"),
        "total_dist": route["distance"],
        "total_time": route["duration"],
    }


@lru_cache(maxsize=200_000)
def route_fast_cached(a_lat: float, a_lon: float, b_lat: float, b_lon: float, profile: str):
    """Only (distance_m, duration_s), no geometry. Cached."""
    base = _base_url(profile)
    coords = f"{a_lon},{a_lat};{b_lon},{b_lat}"
    url = f"{base}/route/v1/{profile}/{coords}?overview=false&steps=false"

    r = SESSION.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok":
        raise RuntimeError(data)
    route = data["routes"][0]
    return route["distance"], route["duration"]


def walk_fast(a: LatLon, b: LatLon) -> tuple:
    return route_fast_cached(q(a[0]), q(a[1]), q(b[0]), q(b[1]), "walking")


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
