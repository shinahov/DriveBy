from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Optional

LatLon = Tuple[float, float]  # (lat, lon)


@dataclass(frozen=True)
class DriverRoute:
    """
    Represents the driver's fixed route (usually profile='driving').
    geometry_latlon: polyline points for map + indexing
    seg_dist_m: distance between geometry points i -> i+1
    cum_dist_m: cumulative distance from start to geometry point i
    nodes: OSM node IDs from OSRM annotations (optional for debug/matching)
    """
    start: LatLon
    dest: LatLon
    dist: float
    duration: int
    profile: str  # e.g. "driving"

    geometry_latlon: List[LatLon]
    seg_dist_m: List[float]
    cum_dist_m: List[float]

    nodes: Optional[List[int]] = None
