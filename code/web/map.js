// Overview of the whole simulation (admin / debug view):
// every match with its route, every agent that is still waiting for a match.

// ---------- connection: what to do with each message type ----------
const socket = new LiveSocket("/ws")
    .on("positions", msg => {
        applyPositions(msg.data);
        applyFocus();
    })
    .on("routes", msg => {
        applyRoutes(msg.data);
        applyFocus();
    });

// ---------- map ----------
const map = L.map("map");

requestAnimationFrame(() => {
    map.setView([51.2562, 7.1508], 12);
    map.invalidateSize(true);
});
map.whenReady(() => map.invalidateSize(true));

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

const infoEl = document.getElementById("info");

// ---------- state ----------
// one entry per match, looked up by its match id (sim_id):
// sims[simId] = {walker: marker, driver: marker, match: MatchLayers or null}
const sims = {};

// agents without a match (grey dots); index-based, they are only dots
const leftoverDriverMarkers = [];
const leftoverWalkerMarkers = [];

// what the user clicked: null = show all, "M:<simId>" = one match, "A:<agentId>" = one agent
let focusedKey = null;
let routesVersion = null;

// ---------- markers ----------
function createWalkerMarker() {
    const html = `
    <svg width="22" height="22" viewBox="0 0 22 22">
      <polygon points="11,2 20,20 2,20" fill="#f59e0b" stroke="#ffffff" stroke-width="2"/>
    </svg>`;
    return L.marker([0, 0], {
        icon: L.divIcon({className: "", html, iconSize: [22, 22], iconAnchor: [11, 11]})
    });
}

function createDriverMarker() {
    return L.marker([0, 0], {
        icon: L.divIcon({
            className: "",
            html: `<div class="pulse-black"></div>`,
            iconSize: [18, 18],
            iconAnchor: [9, 9]
        })
    });
}

function createLeftoverMarker() {
    return L.circleMarker([0, 0], {
        radius: 5, color: "#6b7280", fillColor: "#9ca3af", fillOpacity: 1, weight: 1
    });
}

// ---------- one match ----------
// layers of one match; created the first time the match shows up
function getSim(simId) {
    if (!sims[simId]) {
        const label = simId.slice(0, 8);
        const walker = createWalkerMarker().addTo(map).bindTooltip("Walker " + label);
        const driver = createDriverMarker().addTo(map).bindTooltip("Driver " + label);
        walker.on("click", () => setFocus("M:" + simId));
        driver.on("click", () => setFocus("M:" + simId));
        sims[simId] = {walker, driver, match: null};
    }
    return sims[simId];
}

function removeSim(simId) {
    const s = sims[simId];
    map.removeLayer(s.walker);
    map.removeLayer(s.driver);
    if (s.match) s.match.remove();
    delete sims[simId];
}

function setSimVisible(s, visible) {
    for (const marker of [s.walker, s.driver]) {
        if (visible && !map.hasLayer(marker)) marker.addTo(map);
        if (!visible && map.hasLayer(marker)) map.removeLayer(marker);
    }
    if (s.match) s.match.setVisible(visible);
}

// ---------- leftover agents ----------
// make the marker list exactly n long
function resizeMarkers(markers, n, tooltipPrefix) {
    while (markers.length < n) {
        const m = createLeftoverMarker().addTo(map).bindTooltip(tooltipPrefix + " " + markers.length);
        m.on("click", () => setFocus(m.focusKey));
        markers.push(m);
    }
    while (markers.length > n) {
        map.removeLayer(markers.pop());
    }
}

function updateLeftovers(markers, agents, tooltipPrefix) {
    resizeMarkers(markers, agents.length, tooltipPrefix);
    agents.forEach((a, i) => {
        markers[i].setLatLng([a.lat, a.lon]);
        markers[i].focusKey = "A:" + a.agent_id;
    });
}

// ---------- messages from the server ----------
function applyRoutes(data) {
    const v = (typeof data.routes_version === "number") ? data.routes_version : null;
    if (v !== null && v === routesVersion) return;
    if (v !== null) routesVersion = v;

    let newPoints = [];   // only zoom to matches we have not seen yet
    for (const route of (Array.isArray(data.routes) ? data.routes : [])) {
        if (!MatchLayers.isValid(route)) continue;
        const s = getSim(route.match_id);
        const isNew = !s.match;
        if (s.match) s.match.remove();
        s.match = new MatchLayers(map, route, {label: route.match_id.slice(0, 8)});
        if (isNew) newPoints = newPoints.concat(s.match.allPoints());
    }
    if (newPoints.length > 0) {
        map.fitBounds(newPoints, {padding: [30, 30]});
    }
}

function applyPositions(data) {
    const frames = Array.isArray(data.sims) ? data.sims : [];
    for (const f of frames) {
        const s = getSim(f.sim_id);
        if (f.walker) s.walker.setLatLng([f.walker.lat, f.walker.lon]);
        if (f.driver) s.driver.setLatLng([f.driver.lat, f.driver.lon]);
    }
    // matches that are finished disappear from the map
    const active = new Set(frames.map(f => f.sim_id));
    for (const simId of Object.keys(sims)) {
        if (!active.has(simId)) removeSim(simId);
    }

    const lD = Array.isArray(data.leftover_drivers) ? data.leftover_drivers : [];
    const lW = Array.isArray(data.leftover_walkers) ? data.leftover_walkers : [];
    updateLeftovers(leftoverDriverMarkers, lD, "Left driver");
    updateLeftovers(leftoverWalkerMarkers, lW, "Left walker");

    const t = (typeof data.t_s === "number") ? Math.round(data.t_s) : "?";
    infoEl.textContent =
        "time = " + t + " s\n" +
        "sims = " + frames.length + "\n" +
        "left drivers = " + lD.length + "\n" +
        "left walkers = " + lW.length;
}

// ---------- focus: click a marker to see only that match / agent ----------
function setFocus(key) {
    focusedKey = key;
    infoEl.textContent = "FOCUS = " + focusedKey;
    applyFocus();
}

function applyFocus() {
    const leftovers = [...leftoverDriverMarkers, ...leftoverWalkerMarkers];
    for (const [simId, s] of Object.entries(sims)) {
        setSimVisible(s, !focusedKey || focusedKey === "M:" + simId);
    }
    for (const m of leftovers) {
        const visible = !focusedKey || focusedKey === m.focusKey;
        if (visible && !map.hasLayer(m)) m.addTo(map);
        if (!visible && map.hasLayer(m)) map.removeLayer(m);
    }
}

map.on("dblclick", () => setFocus(null));

// ---------- controls ----------
document.getElementById("btn-open-create").onclick = () => {
    window.open("/web/create.html", "_blank");
};

const speedRange = document.getElementById("speedRange");
const speedVal = document.getElementById("speedVal");
const speedBox = document.getElementById("speedBox");

document.getElementById("btn-speed").onclick = () => {
    speedBox.style.display = speedBox.style.display === "none" ? "block" : "none";
};

speedRange.oninput = () => {
    speedVal.textContent = speedRange.value;
};

// a click somewhere on the map closes the speed box
map.on("click", () => {
    speedBox.style.display = "none";
});

speedRange.onchange = () => {
    socket.send({type: "speed", value: Number(speedRange.value)});
    speedBox.style.display = "none";
};
