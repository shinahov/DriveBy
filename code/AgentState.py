from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple, Optional
from RouteLike import RouteLike

LatLon = Tuple[float, float]


@dataclass
class AgentState:
    route: RouteLike
    start_offset_s: float = 0.0
    time_scale: float = 1.0
    idx: int = 0
    pos: Optional[LatLon] = None
    done: bool = False


    def update_position(self, global_time: float):
        geo = self.route.geometry_latlon
        cum = self.route.cum_time_s

        if global_time <= cum[0]:
            self.idx = 0
            self.pos = geo[0]
            return

        if global_time >= cum[-1]:
            self.idx = len(geo) - 1
            self.pos = geo[-1]
            return

        while self.idx + 1 < len(cum) and cum[self.idx + 1] <= global_time:
            self.idx += 1

        t0, t1 = cum[self.idx], cum[self.idx + 1]
        (lat0, lon0) = geo[self.idx]
        (lat1, lon1) = geo[self.idx + 1]

        a = 0.0 if t1 == t0 else (global_time - t0) / (t1 - t0)
        self.pos = (
            lat0 + a * (lat1 - lat0),
            lon0 + a * (lon1 - lon0),
        )

    def get_pos(self) -> LatLon:
        return self.pos
