from dataclasses import dataclass
from WalkerRoute import WalkerRoute
from DriverRoute import DriverRoute
from DriverRoute import LatLon


@dataclass
class Match:
    driver: DriverRoute
    walker: WalkerRoute
    pickup: LatLon
    dropoff: LatLon
    pick_walk_m: float
    drop_walk_m: float
    total_walk_m: float
    saving_m: float
