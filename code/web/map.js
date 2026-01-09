let ws = null;
let wsReady = false;

function setupWebSocket() {
    ws = new WebSocket("ws://" + window.location.host + "/ws");

    ws.onopen = () => {
        wsReady = true;
        console.log("WebSocket connected");
    };

    ws.onclose = () => {
        wsReady = false;
        console.log("WebSocket disconnected, retrying in 2s...");
        setTimeout(setupWebSocket, 2000);
    };

    ws.onerror = (err) => {
        console.error("WebSocket error:", err);
        ws.close();
    };

    ws.onmessage = (event) => {
        // Handle incoming messages if needed
        const msg = JSON.parse(event.data);
        console.log("WS IN", event.data);


        if (msg.type === "positions") {
            applyPositions(msg.data);
            applyFocus();
        }
        if (msg.type === "routes") {
            applyRoadsVersion(msg.data);
            applyFocus();
        }
    };
}

setupWebSocket();

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
let focusedKey = null;


// Per-simulation layers
// simLayers[i] = { markers:{walker,driver}, lines:{pre,ride,post,w1,w2,pickup,dropoff} }
let simLayers = [];

// Leftover agents markers
let leftoverDriverMarkers = [];
let leftoverWalkerMarkers = [];


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

let roadsVersion = null;

function applyFocus() {
    // no focus: show everything
    if (!focusedKey) {
        for (let i = 0; i < simLayers.length; i++) {
            const s = simLayers[i];

            if (!map.hasLayer(s.markers.walker)) s.markers.walker.addTo(map);
            if (!map.hasLayer(s.markers.driver)) s.markers.driver.addTo(map);

            Object.values(s.lines).forEach(layer => {
                if (layer && !map.hasLayer(layer)) layer.addTo(map);
            });
        }

        leftoverDriverMarkers.forEach(m => { if (!map.hasLayer(m)) m.addTo(map); });
        leftoverWalkerMarkers.forEach(m => { if (!map.hasLayer(m)) m.addTo(map); });

        return;
    }

    // fokus aktiv then : make everything invisible first
    for (let i = 0; i < simLayers.length; i++) {
        const s = simLayers[i];

        if (map.hasLayer(s.markers.walker)) map.removeLayer(s.markers.walker);
        if (map.hasLayer(s.markers.driver)) map.removeLayer(s.markers.driver);

        Object.values(s.lines).forEach(layer => {
            if (layer && map.hasLayer(layer)) map.removeLayer(layer);
        });
    }

    leftoverDriverMarkers.forEach(m => { if (map.hasLayer(m)) map.removeLayer(m); });
    leftoverWalkerMarkers.forEach(m => { if (map.hasLayer(m)) map.removeLayer(m); });


    // focused sim
    if (focusedKey.startsWith("M:")) {
        const parts = focusedKey.split(":");
        const simId = parts[1]; // extract simId

        // find sim layer by simId
        let idx = -1;
        for (let i = 0; i < simLayers.length; i++) {
            const s = simLayers[i];
            const dk = s.markers.driver._key || "";
            const wk = s.markers.walker._key || "";
            if (dk.includes(`M:${simId}:`) || wk.includes(`M:${simId}:`)) {
                idx = i;
                break;
            }
        }
        if (idx === -1) return;

        const s = simLayers[idx];

        // show only this sim
        s.markers.walker.addTo(map);
        s.markers.driver.addTo(map);

        // show lines from this sim
        Object.values(s.lines).forEach(layer => {
            if (layer) layer.addTo(map);
        });
        return;
    }

    // leftover fokus
    if (focusedKey.startsWith("A:")) {
        const id = focusedKey.slice(2);


        for (const m of leftoverDriverMarkers) {
            if (m._key === `A:${id}`) { m.addTo(map); return; }
        }
        for (const m of leftoverWalkerMarkers) {
            if (m._key === `A:${id}`) { m.addTo(map); return; }
        }
    }
}


function applyRoadsVersion(data) {
    const v = (typeof data.routes_version === "number") ? data.routes_version : null;
        if (v !== null && v === roadsVersion) return;
        if (v !== null) roadsVersion = v;
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
        infoEl.textContent = "Routes loaded...";
}

//Routes (load once)
async function tryLoadRoutes() {
    //if (routesLoaded) return;

    try {
        const data = await fetchJsonNoCache("routes.json");
        applyRoadsVersion(data);
    } catch (e) {
        infoEl.textContent = "--error";
    }
    applyFocus();

}


function applyPositions(data) {
    const sims = Array.isArray(data.sims) ? data.sims : [];

        ensureSimLayers(sims.length);

        for (let i = 0; i < sims.length; i++) {
            const s = sims[i];
            const layer = simLayers[i];
            const simId = s.sim_id;

            if (s.walker) {
                const m = layer.markers.walker;
                m.setLatLng([s.walker.lat, s.walker.lon]);

                // key
                m._key = `M:${simId}:W`;

                // click-handler
                if (!m._clickBound) {
                    m.on("click", (e) => {
                        focusedKey = e.target._key;
                        infoEl.textContent = "FOCUS = " + focusedKey;
                        applyFocus();
                    });

                    m._clickBound = true;
                }
            }

            if (s.driver) {
                const m = layer.markers.driver;
                m.setLatLng([s.driver.lat, s.driver.lon]);

                m._key = `M:${simId}:D`;

                if (!m._clickBound) {
                    m.on("click", (e) => {
                        focusedKey = e.target._key;
                        infoEl.textContent = "FOCUS = " + focusedKey;
                        applyFocus();
                    });


                    m._clickBound = true;
                }
            }
        }

        const lD = Array.isArray(data.leftover_drivers) ? data.leftover_drivers : [];
        const lW = Array.isArray(data.leftover_walkers) ? data.leftover_walkers : [];

        ensureCircleMarkers(leftoverDriverMarkers, lD.length, "Left driver");
        ensureCircleMarkers(leftoverWalkerMarkers, lW.length, "Left walker");

        for (let i = 0; i < lD.length; i++) {
            const m = leftoverDriverMarkers[i];
            m.setLatLng([lD[i].lat, lD[i].lon]);

            m._key = `A:${lD[i].agent_id}`;
            if (!m._clickBound) {
                m.on("click", (e) => {
                    focusedKey = e.target._key;
                    infoEl.textContent = "FOCUS = " + focusedKey;
                    applyFocus();
                });

                m._clickBound = true;
            }
        }

        for (let i = 0; i < lW.length; i++) {
            const m = leftoverWalkerMarkers[i];
            m.setLatLng([lW[i].lat, lW[i].lon]);

            m._key = `A:${lW[i].agent_id}`;
            if (!m._clickBound) {
                m.on("click", (e) => {
                    focusedKey = e.target._key;
                    infoEl.textContent = "FOCUS = " + focusedKey;
                    applyFocus();
                });

                m._clickBound = true;
            }
        }


        const t = (typeof data.t_s === "number") ? Math.round(data.t_s) : "?";

        infoEl.textContent =
            "time = " + t + " s\n" +
            "sims = " + sims.length + "\n" +
            "left drivers = " + lD.length + "\n" +
            "left walkers = " + lW.length;
}

// continuous
async function updatePositions() {
    try {
        const data = await fetchJsonNoCache("positions.json");
        applyPositions(data);

    } catch (e) {
        infoEl.textContent = routesLoaded
            ? "Routes loaded..."
            : "Waiting for routes...";
    }
    applyFocus();

}

// controls
document.getElementById("btn-faster").onclick = () => {
    fetch("/faster");
};
document.getElementById("btn-slower").onclick = () => {
    fetch("/slower");
};


document.getElementById("btn-open-create").onclick = () => {
  window.open("/web/create.html", "_blank");
};

const speedRange = document.getElementById("speedRange");
const speedVal = document.getElementById("speedVal");


const btnSpeed = document.getElementById("btn-speed");
const speedBox = document.getElementById("speedBox");

btnSpeed.onclick = () => {
  speedBox.style.display = speedBox.style.display === "none" ? "block" : "none";
};


speedRange.oninput = () => {
  speedVal.textContent = speedRange.value;
};

speedRange.onchange = () => {
  fetch("/speed?value=" + speedRange.value);
  speedBox.style.display = "none";
};

map.on("dblclick", () => {
  focusedKey = null;
  applyFocus();
});





