from dataclasses import dataclass, field
import uuid
from enum import Enum, auto
from typing import Optional, Tuple
from Match import Match
from AgentState import AgentState

LatLon = Tuple[float, float]

class Phase(Enum):
    WALK_TO_PICKUP = auto()
    WAIT_AT_PICKUP = auto()
    RIDE_WITH_DRIVER = auto()
    WALK_FROM_DROPOFF = auto()
    DONE = auto()

@dataclass
class MatchSimulation:
    match: Match
    driver_agent: AgentState
    walk_to_pickup_agent: AgentState
    walk_from_dropoff_agent: AgentState
    match_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    phase: Phase = Phase.WALK_TO_PICKUP
    creation_time_s: float = 0.0
    walker_pos: Optional[LatLon] = None

    def update(self, t_s: float) -> None:
        t = t_s - self.creation_time_s
        # update driver always
        self.driver_agent.update_position(t_s)

        t_walk_to_pickup_end = self.match.walk_route_to_pickup.duration
        t_driver_pickup = self.match.driver_pickup_eta_s
        t_driver_dropoff = self.match.driver_dropoff_eta_s
        t_walk_from_dropoff_end = t_driver_dropoff + self.match.walk_route_from_dropoff.duration

        if t < t_walk_to_pickup_end:
            self.phase = Phase.WALK_TO_PICKUP
            self.walk_to_pickup_agent.update_position(t)
            self.walker_pos = self.walk_to_pickup_agent.get_pos()

        elif t < t_driver_pickup:
            self.phase = Phase.WAIT_AT_PICKUP
            self.walker_pos = self.match.pickup

        elif t < t_driver_dropoff:
            self.phase = Phase.RIDE_WITH_DRIVER
            self.walker_pos = self.driver_agent.get_pos()

        elif t < t_walk_from_dropoff_end:
            self.phase = Phase.WALK_FROM_DROPOFF
            # walker starts this sub-walk at t_driver_dropoff => use local time
            self.walk_from_dropoff_agent.update_position(t - t_driver_dropoff)
            self.walker_pos = self.walk_from_dropoff_agent.get_pos()

        else:
            self.phase = Phase.DONE
            self.walker_pos = self.match.walk_route_from_dropoff.dest

    def get_walker_pos(self) -> LatLon:
        return self.walker_pos

    def get_driver_pos(self) -> LatLon:
        return self.driver_agent.get_pos()
