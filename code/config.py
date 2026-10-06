"""Central settings. Change ports / thresholds here instead of in the code."""

# OSRM servers (see start_osrm.bat)
OSRM_DRIVE = "http://localhost:5000"
OSRM_WALK = "http://localhost:5001"
OSRM_TIMEOUT_S = 60

# Web server
HOST = "127.0.0.1"
PORT = 8000

# Matching
MIN_SAVING_M = 800.0       # a match must save the walker at least this many metres
PICKUP_CANDIDATES = 15     # nearest route points checked as pickup
DROPOFF_CANDIDATES = 10    # nearest route points checked as dropoff
MAX_SNAP_DIST_M = 30.0     # OSRM walk route must start/end this close to pickup/dropoff

# Simulation loop
TICK_SLEEP_S = 0.05        # real seconds between ticks
DEFAULT_SPEED = 1.0        # simulated seconds per tick
