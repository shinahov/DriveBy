from dataclasses import dataclass
from typing import List, Tuple, Optional
from bisect import bisect_right

LatLon = Tuple[float, float]

@dataclass(frozen=True)
class RouteBase:
    geometry_latlon: List[LatLon]
    dist: float
    duration: float
    start: LatLon
    dest: LatLon
    duration_list: List[float]
    cum_time_s: List[float]
    seg_dist_m: List[float]
    cum_dist_m: List[float]

    def get_pos_at_time(self, t_s: float) -> LatLon:
        if not self.geometry_latlon:
            raise ValueError("geometry_latlon is empty")

        if t_s <= 0.0:
            return self.geometry_latlon[0]

        end_t = self.cum_time_s[-1] if self.cum_time_s else self.duration
        if t_s >= end_t:
            return self.geometry_latlon[-1]

        if len(self.geometry_latlon) != len(self.duration_list) + 1 or len(self.cum_time_s) != len(self.duration_list) + 1:
            raise ValueError("Length mismatch: geometry_latlon/cum_time_s must be duration_list + 1")

        i = bisect_right(self.cum_time_s, t_s) - 1
        seg_t = self.duration_list[i]
        if seg_t <= 0.0:
            return self.geometry_latlon[i + 1]

        alpha = (t_s - self.cum_time_s[i]) / seg_t
        lat1, lon1 = self.geometry_latlon[i]
        lat2, lon2 = self.geometry_latlon[i + 1]
        return (lat1 + alpha * (lat2 - lat1), lon1 + alpha * (lon2 - lon1))


@dataclass(frozen=True)
class DriverRoute(RouteBase):
    #start: LatLon
    #dest: LatLon
    #dist: float
    profile: str = "walking"
    nodes: Optional[List[int]] = None


@dataclass(frozen=True)
class WalkerRoute(RouteBase):
    #start: LatLon
    #dest: LatLon
    #dist: float
    profile: str = "driving"
    nodes: Optional[List[int]] = None
