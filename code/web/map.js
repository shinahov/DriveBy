// ---------- Map setup ----------
const map = L.map("map").setView([51.2562, 7.1508], 12);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

const infoEl = document.getElementById("info");

// ---------- State ----------
let routesLoaded = false;

// Driver route split into 3 segments
let lineDriverPre = null;     // start -> pickup (gray)
let lineDriverRide = null;    // pickup -> dropoff (red)
let lineDriverPost = null;    // dropoff -> end (gray)

let lineWalkToPickup = null;      // green dashed
let lineWalkFromDropoff = null;   // green dashed

let pickupMarker = null;
let dropoffMarker = null;

// ---------- Marker styles ----------
function createWalkerTriangleMarker(latlng) {
  // Orange triangle, no external image
  const html = `
    <svg width="22" height="22" viewBox="0 0 22 22">
      <polygon points="11,2 20,20 2,20"
        fill="#f59e0b" stroke="#ffffff" stroke-width="2"/>
    </svg>
  `;
  return L.marker(latlng, {
    icon: L.divIcon({
      className: "",
      html,
      iconSize: [22, 22],
      iconAnchor: [11, 11]
    })
  });
}

function createPulsingMainDriverMarker(latlng) {
  return L.marker(latlng, {
    icon: L.divIcon({
      className: "",
      html: `<div class="pulse-black"></div>`,
      iconSize: [18, 18],
      iconAnchor: [9, 9]
    })
  });
}

const walkerMarker = createWalkerTriangleMarker([0, 0]).addTo(map);
const bestDriverMarker = createPulsingMainDriverMarker([0, 0]).addTo(map);

// Other drivers remain circles
const otherDriverMarkers = [];

function ensureOtherDriverMarkers(n) {
  while (otherDriverMarkers.length < n) {
    const idx = otherDriverMarkers.length;

    const m = L.circleMarker([0, 0], {
      radius: 5,
      color: "#6b7280",
      fillColor: "#9ca3af",
      fillOpacity: 1,
      weight: 1
    }).addTo(map);

    m.bindTooltip("Driver " + idx);
    otherDriverMarkers.push(m);
  }

  while (otherDriverMarkers.length > n) {
    const m = otherDriverMarkers.pop();
    map.removeLayer(m);
  }
}

// ---------- Helpers ----------
async function fetchJsonNoCache(url) {
  const res = await fetch(url + "?ts=" + Date.now());
  if (!res.ok) throw new Error("HTTP " + res.status + " for " + url);
  return await res.json();
}

function dist2(a, b) {
  const dLat = a[0] - b[0];
  const dLon = a[1] - b[1];
  return dLat * dLat + dLon * dLon;
}

function closestIndex(points, target) {
  let bestI = 0;
  let bestD = Infinity;
  for (let i = 0; i < points.length; i++) {
    const d = dist2(points[i], target);
    if (d < bestD) {
      bestD = d;
      bestI = i;
    }
  }
  return bestI;
}

function sliceInclusive(points, a, b) {
  // inclusive slice [a..b]
  return points.slice(a, b + 1);
}

// ---------- Routes (load until available) ----------
async function tryLoadRoutes() {
  if (routesLoaded) return;

  try {
    const data = await fetchJsonNoCache("routes.json");

    const d  = data.driver_route.geometry_latlon;     // [[lat, lon], ...]
    const w1 = data.walk_to_pickup.geometry_latlon;
    const w2 = data.walk_from_dropoff.geometry_latlon;

    const pts = data.points;
    const pickup = pts.pickup;     // [lat, lon]
    const dropoff = pts.dropoff;   // [lat, lon]

    // Find closest indices on driver route for pickup/dropoff
    const iPick = closestIndex(d, pickup);
    const iDrop = closestIndex(d, dropoff);
    const a = Math.min(iPick, iDrop);
    const b = Math.max(iPick, iDrop);

    // Split driver route into 3 segments
    const segPre  = sliceInclusive(d, 0, a);
    const segRide = sliceInclusive(d, a, b);
    const segPost = sliceInclusive(d, b, d.length - 1);

    // Driver segments
    lineDriverPre = L.polyline(segPre, {
      color: "#9ca3af",
      weight: 6,
      opacity: 0.9
    }).addTo(map);

    lineDriverRide = L.polyline(segRide, {
      color: "#dc2626",
      weight: 7,
      opacity: 0.95
    }).addTo(map);

    lineDriverPost = L.polyline(segPost, {
      color: "#9ca3af",
      weight: 6,
      opacity: 0.9
    }).addTo(map);

    // Walking routes (keep green dashed)
    lineWalkToPickup = L.polyline(w1, {
      color: "#16a34a",
      weight: 5,
      opacity: 0.9
    }).addTo(map);

    lineWalkFromDropoff = L.polyline(w2, {
      color: "#16a34a",
      weight: 5,
      opacity: 0.9
    }).addTo(map);

    // Pickup / dropoff markers (make them nicer)
    pickupMarker = L.circleMarker(pickup, {
      radius: 9,
      color: "#7c3aed",
      fillColor: "#a78bfa",
      fillOpacity: 1,
      weight: 2
    }).addTo(map).bindTooltip("Pickup");

    dropoffMarker = L.circleMarker(dropoff, {
      radius: 9,
      color: "#7c3aed",
      fillColor: "#374151",
      fillOpacity: 1,
      weight: 2
    }).addTo(map).bindTooltip("Dropoff");

    // Fit map to all visible route points
    const allPts = d.concat(w1).concat(w2);
    map.fitBounds(allPts, { padding: [30, 30] });

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

    // Walker triangle position
    if (data.walker) {
      walkerMarker.setLatLng([data.walker.lat, data.walker.lon]);
    }

    // Main driver (pulsing black)
    if (data.driver) {
      bestDriverMarker.setLatLng([data.driver.lat, data.driver.lon]);
    }

    // Other drivers
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

document.getElementById("btn-faster").onclick = () => {
  fetch("/faster");
};

document.getElementById("btn-slower").onclick = () => {
  fetch("/slower");
};

// ---------- Scheduling ----------
setInterval(tryLoadRoutes, 300);
setInterval(updatePositions, 200);

// Start immediately
tryLoadRoutes();
updatePositions();
