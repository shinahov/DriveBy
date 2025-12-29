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


const msgEl = document.getElementById("msg");
const btnWalker = document.getElementById("btn-kind-walker");
const btnDriver = document.getElementById("btn-kind-driver");
const btnConfirm = document.getElementById("btn-confirm");
const btnCreate = document.getElementById("btn-create");
const btnCancel = document.getElementById("btn-cancel");

function setMsg(s) {
    msgEl.textContent = s;
}

function logMsg(s) {
    msgEl.textContent += `\n${s}`;
}

function fmt(p) {
    return `${p[0].toFixed(6)}, ${p[1].toFixed(6)}`;
}

function onRouteAvailable(points) {
    map.fitBounds(points, {padding: [30, 30]});
}


// Create-flow state (start/dest picking)

let kind = null;
let step = "choose_kind"; // choose_kind | pick_start | pick_dest | ready
let pendingPoint = null; // [lat, lon]
let startPoint = null;   // [lat, lon]
let destPoint = null;    // [lat, lon]

// Temporary create UI layers
let startMarker = null;
let destMarker = null;
let previewLine = null;

// After Create we enter view mode
let viewMode = "create"; // create | match | agent
let targetMatchId = null;
let targetAgentId = null;
let createdKind = null;  // remember what user created (walker/driver)

// Render layers for my view
let myWalkerMarker = null;
let myDriverMarker = null;
let myLeftoverMarker = null;
let myWalkerIdx = null;
let myDriverIdx = null;

let myRoutePre = null;
let myRouteRide = null;
let myRoutePost = null;
let myWalkToPickup = null;
let myWalkFromDropoff = null;
let myPickup = null;
let myDropoff = null;

// Timers
let statusTimer = null;
let posTimer = null;
let routesTimer = null;


// Helpers: fetching without cache

const walkerIcon = L.icon({
    iconUrl: "icons/walker.png",
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    tooltipAnchor: [0, -12]
});

const driverIcon = L.icon({
    iconUrl: "icons/car.png",
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    tooltipAnchor: [0, -13]
});

const pickDropIcon = L.icon({
    iconUrl: "icons/pick_drop.png",
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    tooltipAnchor: [0, -12]
});

const destIcon = L.icon({
    iconUrl: "icons/dest.png",
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    tooltipAnchor: [0, -12]
});


async function fetchJsonNoCache(url) {
    const res = await fetch(url + "?ts=" + Date.now(), {cache: "no-store"});
    if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
    return await res.json();
}


function clearPreview() {
    if (previewLine) {
        map.removeLayer(previewLine);
        previewLine = null;
    }
}

function redrawPreview() {
    // while picking DEST we want a live visual line from start to current point.
    clearPreview();
    const a = startPoint;
    const b = pendingPoint || destPoint;
    if (a && b) {
        previewLine = L.polyline([a, b], {weight: 3, dashArray: "6,6"}).addTo(map);
    }
}

function resetCreateState() {
    // Reset only the "create selection" state (not the final view mode).
    kind = null;
    step = "choose_kind";
    pendingPoint = null;
    startPoint = null;
    destPoint = null;

    btnConfirm.disabled = true;
    btnCreate.disabled = true;

    if (startMarker) {
        map.removeLayer(startMarker);
        startMarker = null;
    }
    if (destMarker) {
        map.removeLayer(destMarker);
        destMarker = null;
    }
    clearPreview();
}


// creating an agent is asynchronous; backend needs time to match and create simulation.

async function fetchStatus(requestId) {
    const res = await fetch(`/create_status?request_id=${encodeURIComponent(requestId)}`, {cache: "no-store"});
    if (!res.ok) throw new Error(`status HTTP ${res.status}`);
    return await res.json();
}

function stopStatusPolling() {
    if (statusTimer) {
        clearInterval(statusTimer);
        statusTimer = null;
    }
}

function startStatusPolling(requestId) {
    stopStatusPolling();

    statusTimer = setInterval(async () => {
        try {
            const st = await fetchStatus(requestId);

            // Still waiting: keep polling
            if (st.status === "queued" || st.status === "created") return;

            // Done: stop polling
            stopStatusPolling();

            if (st.status === "matched") {
                viewMode = "match";
                targetMatchId = st.match_id;
                targetAgentId = st.agent_id || null;

                setMsg(
                    `Matched.\n` +
                    `match_id = ${targetMatchId}\n` +
                    `Loading match view...`
                );

                // Start rendering loops for the match
                startViewLoops();

            } else if (st.status === "not_matched") {
                viewMode = "agent";
                targetAgentId = st.agent_id;

                setMsg(
                    `No match.\n` +
                    `agent_id = ${targetAgentId}\n` +
                    `Showing your agent...`
                );

                // Start rendering loops for the agent-only view
                startViewLoops();

            } else {
                setMsg(`Unknown status:\n${JSON.stringify(st, null, 2)}`);
            }

        } catch (e) {
            // Hard error: stop; user needs to fix backend endpoint.
            stopStatusPolling();
            setMsg(`Error while polling status:\n${e.message}`);
        }
    }, 300);
}


//clear old my view layers

function removeIfExists(layer) {
    if (layer && map.hasLayer(layer)) map.removeLayer(layer);
    return null;
}

function clearMyViewLayers() {
    myWalkerMarker = removeIfExists(myWalkerMarker);
    myDriverMarker = removeIfExists(myDriverMarker);
    myLeftoverMarker = removeIfExists(myLeftoverMarker);
    myWalkerIdx = null;
    myDriverIdx = null;

    myRoutePre = removeIfExists(myRoutePre);
    myRouteRide = removeIfExists(myRouteRide);
    myRoutePost = removeIfExists(myRoutePost);

    myWalkToPickup = removeIfExists(myWalkToPickup);
    myWalkFromDropoff = removeIfExists(myWalkFromDropoff);

    myPickup = removeIfExists(myPickup);
    myDropoff = removeIfExists(myDropoff);
}


async function updateMyPosition() {
    if (viewMode !== "match" && viewMode !== "agent") return;

    const data = await fetchJsonNoCache("positions.json");

    if (viewMode === "match") {
        const sims = Array.isArray(data.sims) ? data.sims : [];
        const s = sims.find(x => String(x.sim_id) === String(targetMatchId));
        if (!s) return;

        // Show BOTH markers in match view (driver + walker).
        // match is a pair; seeing both helps debugging and makes the view complete.

        if (s.walker && typeof s.walker.lat === "number" && typeof s.walker.lon === "number") {
            const latlng = [s.walker.lat, s.walker.lon];
            if (!myWalkerMarker) {
                myWalkerMarker = L.marker(latlng, {icon: walkerIcon}).addTo(map).bindTooltip("Walker (match)");
            } else {
                myWalkerMarker.setLatLng(latlng);
            }
            myWalkerIdx = Number.isInteger(s.walker.idx) ? s.walker.idx : 0;

        }

        if (s.driver && typeof s.driver.lat === "number" && typeof s.driver.lon === "number") {
            const latlng = [s.driver.lat, s.driver.lon];
            if (!myDriverMarker) {
                myDriverMarker = L.marker(latlng, {icon: driverIcon}).addTo(map).bindTooltip("Driver (match)");
            } else {
                myDriverMarker.setLatLng(latlng);
            }
            myDriverIdx = Number.isInteger(s.driver.idx) ? s.driver.idx : 0;
        }

        return;
    }

    if (viewMode === "agent") {
        const lD = Array.isArray(data.leftover_drivers) ? data.leftover_drivers : [];
        const lW = Array.isArray(data.leftover_walkers) ? data.leftover_walkers : [];

        const a = [...lD, ...lW].find(x => String(x.agent_id) === String(targetAgentId));
        if (!a) return;

        const latlng = [a.lat, a.lon];
        if (!myLeftoverMarker) {
            myLeftoverMarker = L.circleMarker(latlng, {radius: 9, weight: 2, fillOpacity: 1}).addTo(map)
                .bindTooltip("Your agent (unmatched)");
            map.setView(latlng, 14);
        } else {
            myLeftoverMarker.setLatLng(latlng);
        }
    }
}


// routes are only meaningful once a match exists; unmatched agent has no match route.
function sliceInclusive(points, a, b) {
    if (a < 0) a = 0;
    if (b >= points.length) b = points.length - 1;
    if (b < a) return [];
    return points.slice(a, b + 1);
}

async function updateMyRoutes() {
    if (viewMode !== "match") return;

    const data = await fetchJsonNoCache("routes.json");
    const routes = Array.isArray(data.routes) ? data.routes : [];
    const r = routes.find(x => String(x.match_id) === String(targetMatchId));
    if (!r) return;

    const d = r.driver_route?.geometry_latlon;
    const w1 = r.walk_to_pickup?.geometry_latlon;
    const w2 = r.walk_from_dropoff?.geometry_latlon;
    const pickup = r.points?.pickup;
    const dropoff = r.points?.dropoff;

    if (!Array.isArray(d) || !Array.isArray(w1) || !Array.isArray(w2) || !pickup || !dropoff) return;

    const iPick = r.idx?.pickup;
    const iDrop = r.idx?.dropoff;
    if (!Number.isInteger(iPick) || !Number.isInteger(iDrop)) return;

    const a = Math.min(iPick, iDrop);
    const b = Math.max(iPick, iDrop);
    logMsg(
        `driverIdx=${myDriverIdx} ` +
        `routeLen=${d.length} ` +
        `pickup=${a} drop=${b}`
    );


    const dIdx = Number.isInteger(myDriverIdx) ? myDriverIdx : 0; // i dont why ist only works if i do this

    const segPre = sliceInclusive(d, dIdx, a);
    const segRide = sliceInclusive(d, Math.max(dIdx, a), b);
    const segPost = sliceInclusive(d, Math.max(dIdx, b), d.length - 1);

    const all = d.concat(w1, w2);

    // Observe state BEFORE removing (important)
    const hadRouteBefore = !!myRouteRide;

    // Remove old layers
    myRoutePre = removeIfExists(myRoutePre);
    myRouteRide = removeIfExists(myRouteRide);
    myRoutePost = removeIfExists(myRoutePost);
    myWalkToPickup = removeIfExists(myWalkToPickup);
    myWalkFromDropoff = removeIfExists(myWalkFromDropoff);
    myPickup = removeIfExists(myPickup);
    myDropoff = removeIfExists(myDropoff);
    clearPreview();

    // Draw new layers
    myRoutePre = L.polyline(segPre, {weight: 5, opacity: 0.8}).addTo(map).bindTooltip("Driver pre");
    myRouteRide = L.polyline(segRide, {weight: 6, opacity: 0.9, color: "red"}).addTo(map).bindTooltip("Driver ride");
    myRoutePost = L.polyline(segPost, {weight: 5, opacity: 0.8}).addTo(map).bindTooltip("Driver post");

    myWalkToPickup = L.polyline(w1, {weight: 4, opacity: 0.85, dashArray: "6", color: "green"})
        .addTo(map).bindTooltip("Walk to pickup");
    myWalkFromDropoff = L.polyline(w2, {weight: 4, opacity: 0.85, dashArray: "6", color: "green"})
        .addTo(map).bindTooltip("Walk from dropoff");

    myPickup = L.marker(pickup, {icon: pickDropIcon}).addTo(map).bindTooltip("Pickup");
    myDropoff = L.marker(dropoff, {icon: pickDropIcon}).addTo(map).bindTooltip("Dropoff");


    // View policy: only when route appears the first time
    if (!hadRouteBefore && all.length > 0) {
        onRouteAvailable(all);
    }
}


// Start/stop view loops

function stopViewLoops() {
    if (posTimer) {
        clearInterval(posTimer);
        posTimer = null;
    }
    if (routesTimer) {
        clearInterval(routesTimer);
        routesTimer = null;
    }
}

function startViewLoops() {
    // When we switch from create -> match/agent, we want to hide create preview layers
    // and focus only on the target.
    stopViewLoops();
    clearMyViewLayers();

    // Optional: disable create buttons to prevent multiple requests
    btnWalker.disabled = true;
    btnDriver.disabled = true;
    btnConfirm.disabled = true;
    btnCreate.disabled = true;

    // Positions update: frequent
    posTimer = setInterval(() => {
        updateMyPosition().catch(() => {
        });
    }, 200);

    // Routes update: slightly slower
    routesTimer = setInterval(() => {
        updateMyRoutes().catch(() => {
        });
    }, 400);

    // Kick immediately
    updateMyPosition().catch(() => {
    });
    updateMyRoutes().catch(() => {
    });
}


btnWalker.onclick = () => {
    if (viewMode !== "create") return;
    kind = "walker";
    step = "pick_start";
    pendingPoint = null;
    btnConfirm.disabled = true;
    btnCreate.disabled = true;
    setMsg("Walker: click map to select START, then Confirm.");
};

btnDriver.onclick = () => {
    if (viewMode !== "create") return;
    kind = "driver";
    step = "pick_start";
    pendingPoint = null;
    btnConfirm.disabled = true;
    btnCreate.disabled = true;
    setMsg("Driver: click map to select START, then Confirm.");
};

btnCancel.onclick = () => {
    //user wants to close child without touching the main window.
    stopStatusPolling();
    stopViewLoops();
    window.close();
};

btnConfirm.onclick = () => {
    if (viewMode !== "create") return;
    if (!pendingPoint) return;

    if (step === "pick_start") {
        startPoint = pendingPoint;
        pendingPoint = null;
        btnConfirm.disabled = true;
        step = "pick_dest";
        setMsg(`${kind}: START = ${fmt(startPoint)}\nNow click map to select DEST, then Confirm.`);
        redrawPreview();
        return;
    }

    if (step === "pick_dest") {
        destPoint = pendingPoint;
        pendingPoint = null;
        btnConfirm.disabled = true;
        step = "ready";
        btnCreate.disabled = false;
        setMsg(`${kind}: DEST = ${fmt(destPoint)}\nClick Create.`);
        redrawPreview();
    }
};

btnCreate.onclick = async () => {
    if (viewMode !== "create") return;
    if (!kind || !startPoint || !destPoint) return;

    const payload = {
        type: kind,
        start: {lat: startPoint[0], lon: startPoint[1]},
        dest: {lat: destPoint[0], lon: destPoint[1]}
    };

    try {
        // Lock UI to prevent double-submit
        btnCreate.disabled = true;
        btnConfirm.disabled = true;
        btnWalker.disabled = true;
        btnDriver.disabled = true;

        setMsg("Sending create request...");

        const res = await fetch("/create_agent", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            const txt = await res.text();
            throw new Error(`HTTP ${res.status}: ${txt}`);
        }

        const data = await res.json();
        const requestId = data.request_id;

        createdKind = kind;

        setMsg(
            `Request accepted.\n` +
            `request_id = ${requestId}\n` +
            `Waiting for match...`
        );
        if (startMarker) {
            map.removeLayer(startMarker);
            startMarker = null;
        }
        clearPreview();

        // After submit, we are still in create mode but waiting; we do status polling now.
        startStatusPolling(requestId);

    } catch (e) {
        // On error, re-enable selection so the user can try again.
        btnWalker.disabled = false;
        btnDriver.disabled = false;
        btnConfirm.disabled = (!(step === "pick_start" || step === "pick_dest"));
        btnCreate.disabled = (step !== "ready");

        setMsg(`Create failed:\n${e.message}`);
    }
};


// Map click: pick points (create mode only)

map.on("click", (ev) => {
    if (viewMode !== "create") return;
    if (step !== "pick_start" && step !== "pick_dest") return;

    pendingPoint = [ev.latlng.lat, ev.latlng.lng];
    btnConfirm.disabled = false;

    if (step === "pick_start") {
        if (!startMarker) {
            startMarker = L.circleMarker(pendingPoint, {radius: 7, weight: 2, fillOpacity: 1})
                .addTo(map).bindTooltip("START (pending)");
        } else {
            startMarker.setLatLng(pendingPoint);
        }
        setMsg(`Choose ${kind}: START = ${fmt(pendingPoint)}\nClick Confirm to set START.`);
    } else {
        if (!destMarker) {
            destMarker = L.marker(pendingPoint, {icon: destIcon}).addTo(map).bindTooltip("DEST");
        } else {
            destMarker.setLatLng(pendingPoint);
        }
        setMsg(`Choose ${kind}: DEST = ${fmt(pendingPoint)}\nClick Confirm to set DEST.`);

    }

    redrawPreview();
});


//  Init

viewMode = "create";
resetCreateState();
setMsg("Choose agent type.");
