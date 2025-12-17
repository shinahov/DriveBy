from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple, Optional
from RouteBase import RouteBase

LatLon = Tuple[float, float]


@dataclass
class AgentState:
    route: RouteBase
    start_offset_s: float = 0.0
    time_scale: float = 1.0
    idx: int = 0
    pos: Optional[LatLon] = None
    done: bool = False


    def update_position(self, global_time: float):
        self.pos = self.route.get_pos_at_time(global_time)

    def get_pos(self) -> LatLon:
        if self.pos is None:
            raise RuntimeError("Position not set yet. Call update_position() first.")
        return self.pos

