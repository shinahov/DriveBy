// ---------- Map setup ----------
const map = L.map("map").setView([51.2562, 7.1508], 12);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

const infoEl = document.getElementById("info");

// ---------- State ----------
let routesLoaded = false;

let lineDriver = null;
let lineWalkToPickup = null;
let lineWalkFromDropoff = null;

let pickupMarker = null;
let dropoffMarker = null;

const walkerMarker = L.circleMarker([0, 0], { radius: 8 }).addTo(map);
const bestDriverMarker = L.circleMarker([0, 0], { radius: 7 }).addTo(map);

const otherDriverMarkers = [];

// ---------- Marker helpers ----------
function ensureOtherDriverMarkers(n) {
  while (otherDriverMarkers.length < n) {
    const idx = otherDriverMarkers.length;
    const m = L.circleMarker([0, 0], { radius: 5 }).addTo(map);
    m.bindTooltip("Driver " + idx);
    otherDriverMarkers.push(m);
  }

  while (otherDriverMarkers.length > n) {
    const m = otherDriverMarkers.pop();
    map.removeLayer(m);
  }
}

// ---------- Fetch helper ----------
async function fetchJsonNoCache(url) {
  const res = await fetch(url + "?ts=" + Date.now());
  if (!res.ok) {
    throw new Error("HTTP " + res.status + " for " + url);
  }
  return await res.json();
}

// ---------- Routes (load until available) ----------
async function tryLoadRoutes() {
  if (routesLoaded) return;

  try {
    const data = await fetchJsonNoCache("routes.json");

    const d = data.driver_route.geometry_latlon; // [[lat, lon], ...]
    const w1 = data.walk_to_pickup.geometry_latlon;
    const w2 = data.walk_from_dropoff.geometry_latlon;

    lineDriver = L.polyline(d, {
      color: "#1f77b4",
      weight: 6,
      opacity: 0.9
    }).addTo(map);

    lineWalkToPickup = L.polyline(w1, {
      color: "#2ca02c",
      weight: 5,
      opacity: 0.9,
      dashArray: "8 10"
    }).addTo(map);

    lineWalkFromDropoff = L.polyline(w2, {
      color: "#2ca02c",
      weight: 5,
      opacity: 0.9,
      dashArray: "8 10"
    }).addTo(map);

    const pts = data.points;
    pickupMarker = L.circleMarker(pts.pickup, { radius: 7 })
      .addTo(map)
      .bindTooltip("Pickup");

    dropoffMarker = L.circleMarker(pts.dropoff, { radius: 7 })
      .addTo(map)
      .bindTooltip("Dropoff");

    map.fitBounds(d.concat(w1).concat(w2), { padding: [30, 30] });

    routesLoaded = true;
    infoEl.textContent = "Routes loaded.\nWaiting for positions.json ...";
  } catch (e) {
    infoEl.textContent = "Waiting for routes.json ...";
  }
}

// ---------- Positions (continuous updates) ----------
async function updatePositions() {
  try {
    const data = await fetchJsonNoCache("positions.json");

    if (data.walker) {
      walkerMarker.setLatLng([data.walker.lat, data.walker.lon]);
    }

    if (data.driver) {
      bestDriverMarker.setLatLng([data.driver.lat, data.driver.lon]);
    }

    const drivers = Array.isArray(data.drivers) ? data.drivers : [];
    ensureOtherDriverMarkers(drivers.length);

    for (let i = 0; i < drivers.length; i++) {
      otherDriverMarkers[i].setLatLng([drivers[i].lat, drivers[i].lon]);
    }

    const t = (typeof data.t_s === "number") ? Math.round(data.t_s) : "?";
    const phase = data.phase ? data.phase : "-";

    infoEl.textContent =
      "time = " + t + " s\n" +
      "phase = " + phase + "\n" +
      "other drivers = " + drivers.length;

  } catch (e) {
    infoEl.textContent = routesLoaded
      ? "Routes loaded.\nWaiting for positions.json ..."
      : "Waiting for routes.json ...";
  }
}

// ---------- Scheduling ----------
setInterval(tryLoadRoutes, 300);
setInterval(updatePositions, 200);

// Start immediately
tryLoadRoutes();
updatePositions();
