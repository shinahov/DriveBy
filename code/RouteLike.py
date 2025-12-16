from typing import Protocol, List, Tuple

LatLon = Tuple[float, float]


class RouteLike(Protocol):
    geometry_latlon: List[LatLon]
    cum_time_s: List[float]
