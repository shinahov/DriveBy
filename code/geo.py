"""Pure geometry helpers (no network)."""
import math
import random
from typing import List, Tuple

LatLon = Tuple[float, float]


def haversine_m(a: LatLon, b: LatLon) -> float:
    R = 6371000.0
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    x = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def cum_array(values: List[float]) -> List[float]:
    cum = [0.0]
    s = 0.0
    for v in values:
        s += v
        cum.append(s)
    return cum


def topk_by_haversine(points: List[LatLon], target: LatLon, k: int) -> List[int]:
    """Indices of the k points closest to target (straight-line distance)."""
    idx_d = [(i, haversine_m(p, target)) for i, p in enumerate(points)]
    idx_d.sort(key=lambda t: t[1])
    return [i for i, _ in idx_d[:min(k, len(idx_d))]]


def is_within_dist(p1: LatLon, p2: LatLon, max_dist_m: float) -> bool:
    return haversine_m(p1, p2) <= max_dist_m


def random_offset(point: LatLon, radius_m: float) -> LatLon:
    lat, lon = point
    grad = 111320.0
    dlat = random.uniform(-radius_m, radius_m) / grad
    dlon = random.uniform(-radius_m, radius_m) / (grad * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon
