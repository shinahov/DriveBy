from dataclasses import dataclass
from DriverRoute import LatLon, DriverRoute
from WalkerRoute import WalkerRoute

@dataclass
class Match:
    driver: DriverRoute
    walker: WalkerRoute

    pickup: LatLon
    dropoff: LatLon
    pickup_index: int
    dropoff_index: int

    # walking to pickup / from dropoff
    pick_walk_m: float
    drop_walk_m: float
    total_walk_m: float

    pick_walk_s: float
    drop_walk_s: float
    total_walk_s: float

    # ride on driver's route
    ride_m: float
    ride_s: float

    # benefit
    saving_m: float
    saving_s: float

    # driver ETAs relative to driver route start (optional but useful)
    driver_pickup_eta_s: float
    driver_dropoff_eta_s: float
