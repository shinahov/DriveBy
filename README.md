# Real-Time Ride Sharing – Prototype (hobby / concept)

This is a semi-hobby project and still very early stage.  
I hope it can become genuinely useful one day, but right now it’s mainly a concept + technical prototype.

## Concept
Think of it as an “Uber-like” map app, but with a different main idea:

- Drivers are **already traveling** from A → B (they don’t start a trip just to serve a rider).
- Pedestrians (walkers) are going somewhere in the same general direction.
- The system tries to match them so the driver can **pick up a passerby near the route**, drop them off later, and the walker finishes the remaining distance on foot.

So the driver does not fully replace walking — the goal is to reduce walking time/distance by inserting a “ride segment” into the walker’s trip.

## What’s implemented right now
- Uses **OSRM** to fetch routes:
  - driving routes for drivers
  - walking routes for walkers
- Routes are stored as **polylines** (lists of `(lat, lon)` points).
- A matching step that finds:
  - a **pickup point** on the driver polyline that minimizes the walking distance from walker start
  - a **dropoff point** later on the driver polyline that minimizes walking distance to the walker destination
- A “best driver” selection (currently simple) based on travel/walking cost.
- A basic real-time simulation loop:
  - agents move along their polylines over time
  - the backend writes `positions.json` and `routes.json`
- A lightweight frontend using **Leaflet** to visualize:
  - driver + walker positions
  - match routes (drive + walk-to-pickup + walk-from-dropoff)
  - pickup/dropoff markers

## Tech notes (how it works)
- Backend is a Python simulation loop:
  - pulls create requests from a queue (`/create_agent`)
  - computes routes via OSRM
  - tries to match against existing drivers/walkers
  - updates positions each tick (`t += dt`)
  - writes JSON snapshots for the frontend
- Frontend polls JSON files (prototype-style):
  - positions update frequently (e.g. 200ms)
  - routes update slower (e.g. 400ms)
- Matching logic is currently “good enough for a prototype”, but not yet designed for high load.

## What I want to do next
### 1) Fix UI / simulation bugs first
Right now the UI can feel a bit clunky and buggy (state switches, leftover → matched transitions, timing issues).  
Before adding new features, the goal is to make the current flow stable.

### 2) Stable ID flow for real users (multi-tab / multi-user)
Currently this is still prototype-level. The next step is to make a clean ID/session flow so multiple real users can use it without collisions:
- each user/session should reliably track their own agent
- smooth transitions when an unmatched agent becomes matched later
- later this should map naturally to a DB model (agents, matches, sessions)

### 3) Move from polling to WebSockets (once the UI is stable)
Polling JSON works for prototyping, but it won’t scale well.
Once the UI is less buggy, I want to switch to something like:
- WebSockets (push updates to clients)
- or Server-Sent Events
So the frontend gets real-time updates efficiently and reliably.

### 4) Improve the matching algorithm (important for scale)
The matching logic will become critical when many users are active.  
Planned improvements:
- faster candidate search (spatial indexing / bounding boxes / k-nearest)
- stronger feasibility checks (ETA constraints, pickup timing)
- fairer multi-user policies (avoid greedy “first come wins”)
- better objective functions (time saved, detour cost, wait time)


