// request_id of the agent this page created (null until the server queued it)
let myRequestId = null;

// connection to the server: what to do with each message type
const socket = new LiveSocket("/ws_agent")
    .on("position", msg => updateMyPosition(msg.data))
    .on("routes", msg => updateMyRoutes(msg.data))
    .on("status", msg => handleStatus(msg));

// after a reconnect the server no longer knows us -> subscribe again
socket.onConnect = () => {
    if (myRequestId) socket.send({type: "subscribe", request_id: myRequestId});
};

function handleStatus(st) {
    if (st.status === Status.QUEUED) {
        myRequestId = st.request_id;
        setMsg(`Queued.\nrequest_id=${st.request_id}`);
        return;
    }

    if (st.status === Status.NOT_MATCHED) {
        viewMode = "agent";
        targetAgentId = st.agent_id;
        targetMatchId = null;
        setMsg(`No match.\nagent_id=${targetAgentId}`);
        return;
    }

    if (st.status === Status.MATCHED) {
        viewMode = "match";
        targetMatchId = st.match_id;
        targetAgentId = st.agent_id ?? null;
        showFollowButtons();
        setMsg(`Matched.\nmatch_id=${targetMatchId}`);
        return;
    }

    if (st.status === Status.DONE) {
        setMsg("Arrived. Trip finished.");
        return;
    }

    if (st.status === Status.ERROR) {
        setMsg(`Error:\n${st.message}`);
        unlockCreateButtons();
        return;
    }

    console.log("unhandled status:", st.status, st);
}

const map = L.map("map", {
    rotate: true,
    bearing: 0,
    rotateControl: true
});

requestAnimationFrame(() => {
    map.setView([51.2562, 7.1508], 12);
    map.invalidateSize(true);
});

map.whenReady(() => map.invalidateSize(true));

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    maxNativeZoom: 19,
    attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);


const msgEl = document.getElementById("msg");
const btnWalker = document.getElementById("btn-kind-walker");
const btnDriver = document.getElementById("btn-kind-driver");
const btnConfirm = document.getElementById("btn-confirm");
const btnCreate = document.getElementById("btn-create");
const btnCancel = document.getElementById("btn-cancel");
const btnFollow = document.getElementById("btn-follow");
const btnStopFollow = document.getElementById("btn-stop-follow");

function showFollowButtons() {
    btnFollow.hidden = false;
    btnStopFollow.hidden = true;
}

function showStopButton() {
    btnFollow.hidden = true;
    btnStopFollow.hidden = false;
}

function hideFollowButtons() {
    btnFollow.hidden = true;
    btnStopFollow.hidden = true;
}

function setMsg(s) {
    msgEl.textContent = s;
}

function logMsg(s) {
    msgEl.textContent += `\n${s}`;
}

function fmt(p) {
    return `${p[0].toFixed(6)}, ${p[1].toFixed(6)}`;
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
let myWalkerPIdx = null;
let myWalkerDIdx = null;
let myDriverIdx = null;
let driverRoutePoints = null;
let walkerRoutePoints = null;


let myMatch = null;       // MatchLayers of my match (routes + pickup/dropoff)


// follows my agent like a navigation app (navigation.js)
const follower = new MapFollower(map);


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


//clear old my view layers

function removeIfExists(layer) {
    if (layer && map.hasLayer(layer)) map.removeLayer(layer);
    return null;
}

function clearMyViewLayers() {
    myWalkerMarker = removeIfExists(myWalkerMarker);
    myDriverMarker = removeIfExists(myDriverMarker);
    myLeftoverMarker = removeIfExists(myLeftoverMarker);
    myWalkerPIdx = null;
    myWalkerDIdx = null;
    myDriverIdx = null;

    if (myMatch) myMatch.remove();
    myMatch = null;
}


function updateMyPosition(data) {
    if (viewMode !== "match" && viewMode !== "agent") return;

    if (viewMode === "match") {
        const frame = data?.frame;
        if (!frame) return;

        const s = frame;


        if (targetMatchId == null && s.sim_id != null) targetMatchId = s.sim_id;


        if (targetMatchId != null && String(s.sim_id) !== String(targetMatchId)) return;
        if (!s) return;

        // Show BOTH markers in match view (driver + walker).
        // match is a pair; seeing both helps debugging and makes the view complete.

        if (s.walker && typeof s.walker.lat === "number" && typeof s.walker.lon === "number") {
            const latlng = [s.walker.lat, s.walker.lon];
            if (!myWalkerMarker) {
                myWalkerMarker = L.marker(latlng, {icon: walkerIcon})
                    .addTo(map).bindTooltip("Walker (match)");
            } else {
                myWalkerMarker.setLatLng(latlng);
            }
            myWalkerPIdx = Number.isInteger(s.walker.pIdx) ? s.walker.pIdx : 0;
            myWalkerDIdx = Number.isInteger(s.walker.dIdx) ? s.walker.dIdx : 0;

            if (createdKind === "walker") {
                follower.update(latlng, walkerRoutePoints, myWalkerPIdx, 5, 30);
            }

        }

        if (s.driver && typeof s.driver.lat === "number" && typeof s.driver.lon === "number") {
            const latlng = [s.driver.lat, s.driver.lon];
            if (!myDriverMarker) {
                myDriverMarker = L.marker(latlng, {icon: driverIcon})
                    .addTo(map).bindTooltip("Driver (match)");
            } else {
                myDriverMarker.setLatLng(latlng);
            }
            myDriverIdx = Number.isInteger(s.driver.idx) ? s.driver.idx : 0;
            if (createdKind === "driver") {
                follower.update(latlng, driverRoutePoints, myDriverIdx, 20, 60);
            }
        }

        updateMyProgress();
        return;
    }

    if (viewMode === "agent") {
        const lD = Array.isArray(data.leftover_drivers) ? data.leftover_drivers : [];
        const lW = Array.isArray(data.leftover_walkers) ? data.leftover_walkers : [];

        const a = [...lD, ...lW].find(x => String(x.agent_id) === String(targetAgentId));
        if (!a) {
            // maybe matched now
            const sims = Array.isArray(data.sims) ? data.sims : [];
            const sim = sims.find(s =>
                String(s.driver?.agent_id) === String(targetAgentId) ||
                String(s.walker?.agent_id) === String(targetAgentId)
            );

            if (sim) {
                viewMode = "match";
                targetMatchId = sim.sim_id; // sim_id == match_id in your JSON
                setMsg(`Agent matched. Switching to match view...\nmatch_id=${targetMatchId}`);
                clearMyViewLayers(); // remove leftover marker + old layers
            }
            return;
        }

        const latlng = [a.lat, a.lon];
        if (!myLeftoverMarker) {
            myLeftoverMarker = L.circleMarker(latlng,
                {radius: 9, weight: 2, fillOpacity: 1}).addTo(map)
                .bindTooltip("Your agent (unmatched)");
            map.setView(latlng, 14);
        } else {
            myLeftoverMarker.setLatLng(latlng);
        }
    }
}


// the server sends the routes of my match once (and again after a reconnect)
function updateMyRoutes(data) {
    if (viewMode !== "match") return;

    const routes = Array.isArray(data.routes) ? data.routes : [];
    const route = routes.find(r => String(r.match_id) === String(targetMatchId));
    if (!route || !MatchLayers.isValid(route)) return;

    const firstTime = !myMatch;
    if (myMatch) myMatch.remove();
    myMatch = new MatchLayers(map, route, {pointIcon: pickDropIcon});
    updateMyProgress();

    driverRoutePoints = myMatch.driver;
    walkerRoutePoints = myMatch.walkTo.concat(myMatch.walkFrom);
    clearPreview();

    if (firstTime) map.fitBounds(myMatch.allPoints(), {padding: [30, 30]});
}

// hide the parts of my match route that are already done
function updateMyProgress() {
    if (!myMatch) return;
    myMatch.setProgress({
        driverIdx: myDriverIdx ?? 0,
        walkToIdx: myWalkerPIdx ?? 0,
        walkFromIdx: myWalkerDIdx ?? 0,
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

function lockCreateButtons() {
    btnCreate.disabled = true;
    btnConfirm.disabled = true;
    btnWalker.disabled = true;
    btnDriver.disabled = true;
}

function unlockCreateButtons() {
    btnWalker.disabled = false;
    btnDriver.disabled = false;
    btnConfirm.disabled = !(step === "pick_start" || step === "pick_dest");
    btnCreate.disabled = (step !== "ready");
}

btnCreate.onclick = () => {
    if (viewMode !== "create") return;
    if (!kind || !startPoint || !destPoint) return;

    const payload = {
        type: kind,
        start: {lat: startPoint[0], lon: startPoint[1]},
        dest: {lat: destPoint[0], lon: destPoint[1]}
    };

    lockCreateButtons();  // prevent double-submit
    setMsg("Sending create request...");
    createdKind = kind;

    if (!socket.send({type: "create_request", payload})) {
        setMsg("Not connected to the server yet. Try again in a moment.");
        unlockCreateButtons();
    }
};

btnFollow.onclick = () => {
    follower.start();
    showStopButton();
};

btnStopFollow.onclick = () => {
    follower.stop();
    showFollowButtons();
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
