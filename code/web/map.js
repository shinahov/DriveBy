// connection to the server: what to do with each message type
const socket = new LiveSocket("/ws")
    .on("positions", msg => {
        applyPositions(msg.data);
        applyFocus();
    })
    .on("routes", msg => {
        applyRoadsVersion(msg.data);
        applyFocus();
    });

// map setup
let map = L.map("map");

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
let focusedKey = null;


// One entry per match, looked up by its match id (sim_id):
// simLayers[simId] = { markers:{walker,driver}, lines:{pre,ride,post,w1,w2,pickup,dropoff} }
let simLayers = {};

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

// layers of one match; created the first time the match shows up
function getSimLayer(simId) {
    if (!simLayers[simId]) {
        const walker = createWalkerTriangleMarker([0, 0]).addTo(map);
        walker.bindTooltip("Walker " + simId.slice(0, 8));
        walker.on("click", () => setFocus(`M:${simId}:W`));

        const driver = createPulsingDriverMarker([0, 0]).addTo(map);
        driver.bindTooltip("Driver " + simId.slice(0, 8));
        driver.on("click", () => setFocus(`M:${simId}:D`));

        simLayers[simId] = {
            markers: {walker, driver},
            lines: {
                pre: null, ride: null, post: null,
                w1: null, w2: null,
                pickup: null, dropoff: null
            }
        };
    }
    return simLayers[simId];
}

// remove the layers of every match that is no longer in activeIds
function removeSimLayersExcept(activeIds) {
    for (const simId of Object.keys(simLayers)) {
        if (activeIds.has(simId)) continue;
        const s = simLayers[simId];
        map.removeLayer(s.markers.walker);
        map.removeLayer(s.markers.driver);
        clearSimLines(s);
        delete simLayers[simId];
    }
}

function setFocus(key) {
    focusedKey = key;
    infoEl.textContent = "FOCUS = " + focusedKey;
    applyFocus();
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
        for (const s of Object.values(simLayers)) {
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
    for (const s of Object.values(simLayers)) {
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
        const simId = focusedKey.split(":")[1];  // "M:<simId>:W" -> <simId>
        const s = simLayers[simId];
        if (!s) return;

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

        let allPts = [];

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

            const s = getSimLayer(r.match_id);
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

        infoEl.textContent = "Routes loaded...";
}

function applyPositions(data) {
    const sims = Array.isArray(data.sims) ? data.sims : [];

        for (const s of sims) {
            const layer = getSimLayer(s.sim_id);
            if (s.walker) layer.markers.walker.setLatLng([s.walker.lat, s.walker.lon]);
            if (s.driver) layer.markers.driver.setLatLng([s.driver.lat, s.driver.lon]);
        }
        // matches that are finished disappear from the map
        removeSimLayersExcept(new Set(sims.map(s => s.sim_id)));

        const lD = Array.isArray(data.leftover_drivers) ? data.leftover_drivers : [];
        const lW = Array.isArray(data.leftover_walkers) ? data.leftover_walkers : [];

        ensureCircleMarkers(leftoverDriverMarkers, lD.length, "Left driver");
        ensureCircleMarkers(leftoverWalkerMarkers, lW.length, "Left walker");

        for (let i = 0; i < lD.length; i++) {
            const m = leftoverDriverMarkers[i];
            m.setLatLng([lD[i].lat, lD[i].lon]);

            m._key = `A:${lD[i].agent_id}`;
            if (!m._clickBound) {
                m.on("click", (e) => setFocus(e.target._key));

                m._clickBound = true;
            }
        }

        for (let i = 0; i < lW.length; i++) {
            const m = leftoverWalkerMarkers[i];
            m.setLatLng([lW[i].lat, lW[i].lon]);

            m._key = `A:${lW[i].agent_id}`;
            if (!m._clickBound) {
                m.on("click", (e) => setFocus(e.target._key));

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

// controls


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
  const v = Number(speedRange.value);
  socket.send({type: "speed", value: v});
  speedBox.style.display = "none";
};

map.on("dblclick", () => {
  focusedKey = null;
  applyFocus();
});





