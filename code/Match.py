from dataclasses import dataclass
from RouteBase import LatLon, DriverRoute, WalkerRoute, RouteBase


@dataclass
class Match:
    driver: RouteBase
    walker: RouteBase
    walk_route_to_pickup: WalkerRoute  # walker_start -> pickup
    walk_route_from_dropoff: WalkerRoute  # dropoff -> walker_dest

    pickup: LatLon
    dropoff: LatLon
    pickup_index: int
    dropoff_index: int

    # walking to pickup / from dropoff
    pick_walk_dist_meters: float
    drop_walk_dist_meters: float
    total_walk_dist_meters: float

    pick_walk_duration_seconds: float
    drop_walk_duration_seconds: float
    total_walk_duration_seconds: float

    # ride on driver's route
    ride_dist_meters: float
    ride_duration_seconds: float

    # benefit
    saving_dist_meters: float
    saving_duration_seconds: float

    # driver ETAs relative to driver route start (optional but useful)
    driver_pickup_eta_s: float
    driver_dropoff_eta_s: float
