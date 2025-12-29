from __future__ import annotations

import uuid
from typing import Tuple, Optional
from RouteBase import RouteBase
from dataclasses import dataclass, field

LatLon = Tuple[float, float]


@dataclass
class AgentState:
    route: RouteBase
    agent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    start_offset_s: float = 0.0
    time_scale: float = 1.0
    idx: int = 0
    pos: Optional[LatLon] = None
    done: bool = False
    assigned: bool = False

    def update_position(self, global_time: float) -> None:
        if self.done:
            return

        t_rel = (global_time - self.start_offset_s) * self.time_scale

        # not started yet -> stay at route start
        if t_rel <= 0.0:
            self.pos = self.route.geometry_latlon[0]
            return

        end_t = self.route.cum_time_s[-1] if self.route.cum_time_s else self.route.duration
        if t_rel >= end_t:
            self.pos = self.route.geometry_latlon[-1]
            self.done = True
            return

        self.pos, self.idx = self.route.get_pos_at_time(t_rel)

    def get_pos(self) -> LatLon:
        if self.pos is None:
            raise RuntimeError("Position not set yet. Call update_position() first.")
        return self.pos

    def __eq__(self, other):
        if not isinstance(other, AgentState):
            return NotImplemented
        return self.agent_id == other.agent_id

    def __hash__(self):
        return hash(self.agent_id)

