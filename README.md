# Real-Time Ride Sharing – Prototype

## Overview
This repository is an **early-stage prototype** for a real-time, non-commercial ride-sharing concept that matches **drivers already traveling along a route** with **nearby pedestrians** heading in a similar direction.  
The focus is on **routing, matching logic, and map visualization** using OSRM and GPS polylines.

---

## Current State (Implemented So Far)
- Fetches **driving** and **walking** routes from **OSRM**.
- Represents routes as **polylines** (lists of `(lat, lon)` points).
- Generates multiple randomized driver routes around a base start/destination (simulation of many drivers).
- Computes:
  - **pickup** point on the driver route (min walking distance to walker start)
  - **dropoff** point after pickup (min walking distance to walker destination)
- Chooses the **best driver** based on minimal total walking distance.
- Visualizes on a **Folium map**:
  - all drivers in **gray**
  - best driver in **blue**
  - walker route in **red**
  - pickup/dropoff markers
  - optional walking paths (dashed)

---

## Planned Next Step (Real-Time Simulation)
Goal: build a **dynamic real-time simulation** where participant positions update continuously.

Planned features:
- Simulate movement of:
  - drivers along their polylines
  - walkers along their walking paths
- Periodic position updates (e.g., every `x` seconds):
  - update current GPS position per participant
  - recompute feasible pickup/dropoff while routes evolve
  - re-evaluate best driver as conditions change
- Visualization options:
  - refreshable map output (prototype approach)
  - or a small live frontend (later) for real-time rendering

---

## Longer-Term Ideas (After Simulation)
- Add temporal constraints (ETA feasibility: walker reaches pickup in time).
- Multi-driver / multi-walker matching policies.
- Safety & verification concepts (out of scope for current code prototype).

---

## Notes
This is a **prototype** under active development. Architecture and functions may change frequently.

## Disclaimer
Educational / experimental only. No commercial or legal assumptions are implemented.
