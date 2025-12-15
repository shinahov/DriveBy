from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Optional

LatLon = Tuple[float, float]  # (lat, lon)


@dataclass(frozen=True)
class WalkerRoute:
    """
    Represents the walker's route (usually profile='walking').
    Same structure as DriverRoute so you can reuse utilities.
    """
    start: LatLon
    dest: LatLon
    dist: float
    duration : int
    profile: str  # e.g. "walking"

    geometry_latlon: List[LatLon]
    seg_dist_m: List[float]
    cum_dist_m: List[float]

    nodes: Optional[List[int]] = None
