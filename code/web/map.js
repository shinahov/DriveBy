// map.js (multi-simulation version)
//alert("map.js loaded");

// map setup
const map = L.map("map");

requestAnimationFrame(() => {
    map.setView([51.2562, 7.1508], 12);
    map.invalidateSize(true);
});


map.whenReady(() => {
    map.invalidateSize(true);
});


L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

const infoEl = document.getElementById("info");

// ---------- State ----------
let routesLoaded = false;

// Per-simulation layers
// simLayers[i] = { markers:{walker,driver}, lines:{pre,ride,post,w1,w2,pickup,dropoff} }
let simLayers = [];

// Leftover agents markers
let leftoverDriverMarkers = [];
let leftoverWalkerMarkers = [];

// helpers
async function fetchJsonNoCache(url) {
    const res = await fetch(url + "?ts=" + Date.now(), {cache: "no-store"});
    if (!res.ok) throw new Error("HTTP " + res.status + " for " + url);
    return await res.json();
}

function sliceInclusive(points, a, b) {
    if (a < 0) a = 0;
    if (b >= points.length) b = points.length - 1;
    if (b < a) return [];
    return points.slice(a, b + 1);
}

// Markers
function createWalkerTriangleMarker(latlng) {
    const html = `
    <svg width="22" height="22" viewBox="0 0 22 22">
      <polygon points="11,2 20,20 2,20" fill="#f59e0b" stroke="#ffffff" stroke-width="2"/>
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

function createPulsingDriverMarker(latlng) {
    return L.marker(latlng, {
        icon: L.divIcon({
            className: "",
            html: `<div class="pulse-black"></div>`,
            iconSize: [18, 18],
            iconAnchor: [9, 9]
        })
    });
}

function ensureSimLayers(n) {
    while (simLayers.length < n) {
        const idx = simLayers.length;

        const walker = createWalkerTriangleMarker([0, 0]).addTo(map);
        walker.bindTooltip("Walker sim " + idx);

        const driver = createPulsingDriverMarker([0, 0]).addTo(map);
        driver.bindTooltip("Driver sim " + idx);

        simLayers.push({
            markers: {walker, driver},
            lines: {
                pre: null, ride: null, post: null,
                w1: null, w2: null,
                pickup: null, dropoff: null
            }
        });
    }

    while (simLayers.length > n) {
        const s = simLayers.pop();
        map.removeLayer(s.markers.walker);
        map.removeLayer(s.markers.driver);
        Object.values(s.lines).forEach(layer => {
            if (layer) map.removeLayer(layer);
        });
    }
}

function ensureCircleMarkers(arr, n, tooltipPrefix) {
    while (arr.length < n) {
        const idx = arr.length;
        const m = L.circleMarker([0, 0], {
            radius: 5,
            color: "#6b7280",
            fillColor: "#9ca3af",
            fillOpacity: 1,
            weight: 1
        }).addTo(map);
        m.bindTooltip(tooltipPrefix + " " + idx);
        arr.push(m);
    }

    while (arr.length > n) {
        map.removeLayer(arr.pop());
    }
}

function clearSimLines(sim) {
    Object.keys(sim.lines).forEach(k => {
        const layer = sim.lines[k];
        if (layer) {
            map.removeLayer(layer);
            sim.lines[k] = null;
        }
    });
}

// ---------- Routes (load once) ----------
async function tryLoadRoutes() {
    if (routesLoaded) return;

    try {
        const data = await fetchJsonNoCache("routes.json");
        const routes = Array.isArray(data.routes) ? data.routes : [];

        ensureSimLayers(routes.length);

        let allPts = [];
        if (allPts.length > 0) {
            map.fitBounds(allPts, {padding: [50, 50]});
        }


        for (let i = 0; i < routes.length; i++) {
            const r = routes[i];
            const d = r.driver_route?.geometry_latlon;
            const w1 = r.walk_to_pickup?.geometry_latlon;
            const w2 = r.walk_from_dropoff?.geometry_latlon;
            const pickup = r.points?.pickup;
            const dropoff = r.points?.dropoff;

            if (!Array.isArray(d) || !Array.isArray(w1) || !Array.isArray(w2) || !pickup || !dropoff) {
                continue;
            }

            const s = simLayers[i];
            clearSimLines(s);

            const iPick = r.idx?.pickup;
            const iDrop = r.idx?.dropoff;
            if (!Number.isInteger(iPick) || !Number.isInteger(iDrop)) continue;
            const a = Math.min(iPick, iDrop);
            const b = Math.max(iPick, iDrop);

            const segPre = sliceInclusive(d, 0, a);
            const segRide = sliceInclusive(d, a, b);
            const segPost = sliceInclusive(d, b, d.length - 1);

            s.lines.pre = L.polyline(segPre, {
                color: "#9ca3af",
                weight: 5,
                opacity: 0.8
            }).addTo(map).bindTooltip("Driver pre sim " + i);

            s.lines.ride = L.polyline(segRide, {
                color: "#dc2626",
                weight: 6,
                opacity: 0.9
            }).addTo(map).bindTooltip("Driver ride sim " + i);

            s.lines.post = L.polyline(segPost, {
                color: "#9ca3af",
                weight: 5,
                opacity: 0.8
            }).addTo(map).bindTooltip("Driver post sim " + i);

            s.lines.w1 = L.polyline(w1, {
                color: "#16a34a",
                weight: 4,
                opacity: 0.85,
                dashArray: "6"
            }).addTo(map).bindTooltip("Walk to pickup sim " + i);

            s.lines.w2 = L.polyline(w2, {
                color: "#16a34a",
                weight: 4,
                opacity: 0.85,
                dashArray: "6"
            }).addTo(map).bindTooltip("Walk from dropoff sim " + i);

            s.lines.pickup = L.circleMarker(pickup, {
                radius: 7,
                color: "#7c3aed",
                fillColor: "#a78bfa",
                fillOpacity: 1,
                weight: 2
            }).addTo(map).bindTooltip("Pickup sim " + i);

            s.lines.dropoff = L.circleMarker(dropoff, {
                radius: 7,
                color: "#7c3aed",
                fillColor: "#374151",
                fillOpacity: 1,
                weight: 2
            }).addTo(map).bindTooltip("Dropoff sim " + i);

            allPts = allPts.concat(d, w1, w2);
        }

        if (allPts.length > 0) {
            map.fitBounds(allPts, {padding: [30, 30]});
        }

        routesLoaded = true;
        infoEl.textContent = "Routes loaded.\nWaiting for positions.json ...";
    } catch (e) {
        infoEl.textContent = "Waiting for routes.json ...";
    }
}

// ---------- Positions (continuous) ----------
async function updatePositions() {
    try {
        const data = await fetchJsonNoCache("positions.json");
        const sims = Array.isArray(data.sims) ? data.sims : [];

        ensureSimLayers(sims.length);

        for (let i = 0; i < sims.length; i++) {
            const s = sims[i];
            const layer = simLayers[i];

            if (s.walker) {
                layer.markers.walker.setLatLng([s.walker.lat, s.walker.lon]);
            }
            if (s.driver) {
                layer.markers.driver.setLatLng([s.driver.lat, s.driver.lon]);
            }
        }

        const lD = Array.isArray(data.leftover_drivers) ? data.leftover_drivers : [];
        const lW = Array.isArray(data.leftover_walkers) ? data.leftover_walkers : [];

        ensureCircleMarkers(leftoverDriverMarkers, lD.length, "Left driver");
        ensureCircleMarkers(leftoverWalkerMarkers, lW.length, "Left walker");

        for (let i = 0; i < lD.length; i++) {
            leftoverDriverMarkers[i].setLatLng([lD[i].lat, lD[i].lon]);
        }
        for (let i = 0; i < lW.length; i++) {
            leftoverWalkerMarkers[i].setLatLng([lW[i].lat, lW[i].lon]);
        }

        const t = (typeof data.t_s === "number") ? Math.round(data.t_s) : "?";

        infoEl.textContent =
            "time = " + t + " s\n" +
            "sims = " + sims.length + "\n" +
            "left drivers = " + lD.length + "\n" +
            "left walkers = " + lW.length;

    } catch (e) {
        infoEl.textContent = routesLoaded
            ? "Routes loaded.\nWaiting for positions.json ..."
            : "Waiting for routes.json ...";
    }
}

// controls
document.getElementById("btn-faster").onclick = () => {
    fetch("/faster");
};
document.getElementById("btn-slower").onclick = () => {
    fetch("/slower");
};

//scheduling
setInterval(tryLoadRoutes, 300);
setInterval(updatePositions, 200);

// Start immediately
tryLoadRoutes();
updatePositions();

// create agent

let createMode = false;
let pickTarget = null;
let newStart = null;
let newDest = null;

let tmpStartMarker = null;
let tmpDestMarker = null;
let tmpLine = null;

function setCreateUiEnabled(on) {
    document.getElementById("btn-set-start").disabled = !on;
    document.getElementById("btn-set-dest").disabled = !on;
    document.getElementById("btn-create-agent").disabled = !on;
    document.getElementById("btn-cancel-agent").disabled = !on;

}

// toggle create mode
function clearTempLayers() {
    if (tmpStartMarker) {
        map.removeLayer(tmpStartMarker);
        tmpStartMarker = null;
    }
    if (tmpDestMarker) {
        map.removeLayer(tmpDestMarker);
        tmpDestMarker = null;
    }
    if (tmpLine) {
        map.removeLayer(tmpLine);
        tmpLine = null;
    }
}

// drew temp markers/line
function redrawTemp() {
    clearTempLayers();

    if (newStart) {
        tmpStartMarker = L.circleMarker(newStart, {
            radius: 7, weight: 2, fillOpacity: 1
        }).addTo(map).bindTooltip("New agent START");
    }
    if (newDest) {
        tmpDestMarker = L.circleMarker(newDest, {
            radius: 7, weight: 2, fillOpacity: 1
        }).addTo(map).bindTooltip("New agent DEST");
    }
    if (newStart && newDest) {
        tmpLine = L.polyline([newStart, newDest], {weight: 3, dashArray: "4"}).addTo(map);
    }
}

//
function updateCreateInfo() {
  const s = newStart ? `${newStart[0].toFixed(6)}, ${newStart[1].toFixed(6)}` : "-";
  const d = newDest ? `${newDest[0].toFixed(6)}, ${newDest[1].toFixed(6)}` : "-";
  const mode = createMode ? `CREATE MODE (${pickTarget || "choose start/dest"})` : "normal";

  infoEl.textContent =
    `mode: ${mode}\n` +
    `new start: ${s}\n` +
    `new dest:  ${d}\n`;
}


document.getElementById("btn-add-agent").onclick = () => {
    createMode = true;
    pickTarget = "start";
    newStart = null;
    newDest = null;
    setCreateUiEnabled(true);
    redrawTemp();
    updateCreateInfo();
};

document.getElementById("btn-set-start").onclick = () => {
    if (!createMode) return;
    pickTarget = "start";
    updateCreateInfo();
};

document.getElementById("btn-set-dest").onclick = () => {
    if (!createMode) return;
    pickTarget = "dest";
    updateCreateInfo();
};

document.getElementById("btn-cancel-agent").onclick = () => {
    createMode = false;
    pickTarget = null;
    newStart = null;
    newDest = null;
    setCreateUiEnabled(false);
    clearTempLayers();
    updateCreateInfo();
};

document.getElementById("btn-create-agent").onclick = async () => {
    if (!createMode) return;
    if (!newStart || !newDest) {
        alert("Please set start and dest by clicking on the map.");
        return;
    }

    // Example payload - adapt to what backend expects
    const payload = {
        type: "walker",     // or "driver" (add a dropdown later)
        start: {lat: newStart[0], lon: newStart[1]},
        dest: {lat: newDest[0], lon: newDest[1]},
    };

    try {
        const res = await fetch("/create_agent", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            const txt = await res.text();
            throw new Error(`HTTP ${res.status}: ${txt}`);
        }

        // success -> reset UI
        createMode = false;
        pickTarget = null;
        newStart = null;
        newDest = null;
        setCreateUiEnabled(false);
        clearTempLayers();
        updateCreateInfo();
    } catch (e) {
        alert("Create agent failed: " + e.message);
    }
};

// Map click capture
map.on("click", (ev) => {
    if (!createMode) return;
    if (!pickTarget) return;

    const lat = ev.latlng.lat;
    const lon = ev.latlng.lng;

    if (pickTarget === "start") newStart = [lat, lon];
    if (pickTarget === "dest") newDest = [lat, lon];

    redrawTemp();
    updateCreateInfo();
});

// init
setCreateUiEnabled(false);