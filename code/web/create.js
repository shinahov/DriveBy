// Page for ONE user: create a walker or driver, then watch it (and its match).
// Parts: CreateFlow (create_flow.js) picks start/dest, MatchLayers (match_layers.js)
// draws the match, MapFollower (navigation.js) follows the agent.

// ---------- map ----------
const map = L.map("map", {rotate: true, bearing: 0, rotateControl: true});

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

const icon = (file, size) => L.icon({
    iconUrl: "icons/" + file,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    tooltipAnchor: [0, -size / 2]
});
const walkerIcon = icon("walker.png", 24);
const driverIcon = icon("car.png", 26);
const pickDropIcon = icon("pick_drop.png", 24);

// ---------- panel ----------
const msgEl = document.getElementById("msg");
const btnFollow = document.getElementById("btn-follow");
const btnStopFollow = document.getElementById("btn-stop-follow");

function setMsg(text) {
    msgEl.textContent = text;
}

function showFollowButtons() {
    btnFollow.hidden = false;
    btnStopFollow.hidden = true;
}

function showStopButton() {
    btnFollow.hidden = true;
    btnStopFollow.hidden = false;
}

// ---------- state ----------
let viewMode = "create";   // create -> agent (waiting for a match) -> match
let myRequestId = null;    // request_id of my agent (null until the server queued it)
let createdKind = null;    // "walker" | "driver"
let targetMatchId = null;
let targetAgentId = null;

// what is drawn for my agent
let myWalkerMarker = null;
let myDriverMarker = null;
let myLeftoverMarker = null;
let myMatch = null;        // MatchLayers of my match
let myDriverIdx = null;    // progress along the routes (indices into the point lists)
let myWalkerPIdx = null;
let myWalkerDIdx = null;
let driverRoutePoints = null;
let walkerRoutePoints = null;

const follower = new MapFollower(map);

const createFlow = new CreateFlow(map, {
    isActive: () => viewMode === "create",
    setMsg,
    onCreate: payload => {
        createdKind = payload.type;
        return socket.send({type: "create_request", payload});
    },
});

// ---------- connection: what to do with each message type ----------
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
        createFlow.unlock();
        return;
    }

    console.log("unhandled status:", st.status, st);
}

// ---------- drawing my agent ----------
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

// create the marker the first time, move it afterwards
function placeMarker(marker, latlng, makeMarker) {
    if (marker) return marker.setLatLng(latlng);
    return makeMarker(latlng).addTo(map);
}

function updateMyPosition(data) {
    if (viewMode === "match") updateMatchPosition(data?.frame);
    if (viewMode === "agent") updateAgentPosition(data);
}

// both agents of my match (frame = one entry of the server's position message)
function updateMatchPosition(frame) {
    if (!frame) return;
    if (targetMatchId == null && frame.sim_id != null) targetMatchId = frame.sim_id;
    if (String(frame.sim_id) !== String(targetMatchId)) return;

    if (frame.walker) {
        const latlng = [frame.walker.lat, frame.walker.lon];
        myWalkerMarker = placeMarker(myWalkerMarker, latlng,
            p => L.marker(p, {icon: walkerIcon}).bindTooltip("Walker (match)"));
        myWalkerPIdx = Number.isInteger(frame.walker.pIdx) ? frame.walker.pIdx : 0;
        myWalkerDIdx = Number.isInteger(frame.walker.dIdx) ? frame.walker.dIdx : 0;
        if (createdKind === "walker") {
            follower.update(latlng, walkerRoutePoints, myWalkerPIdx, 5, 30);
        }
    }

    if (frame.driver) {
        const latlng = [frame.driver.lat, frame.driver.lon];
        myDriverMarker = placeMarker(myDriverMarker, latlng,
            p => L.marker(p, {icon: driverIcon}).bindTooltip("Driver (match)"));
        myDriverIdx = Number.isInteger(frame.driver.idx) ? frame.driver.idx : 0;
        if (createdKind === "driver") {
            follower.update(latlng, driverRoutePoints, myDriverIdx, 20, 60);
        }
    }

    updateMyProgress();
}

// my agent while it waits for a match
function updateAgentPosition(data) {
    const lD = Array.isArray(data.leftover_drivers) ? data.leftover_drivers : [];
    const lW = Array.isArray(data.leftover_walkers) ? data.leftover_walkers : [];
    const a = [...lD, ...lW].find(x => String(x.agent_id) === String(targetAgentId));
    if (!a) return;

    const latlng = [a.lat, a.lon];
    if (!myLeftoverMarker) map.setView(latlng, 14);
    myLeftoverMarker = placeMarker(myLeftoverMarker, latlng,
        p => L.circleMarker(p, {radius: 9, weight: 2, fillOpacity: 1}).bindTooltip("Your agent (unmatched)"));
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
    createFlow.clearPreview();

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

// ---------- buttons ----------
btnFollow.onclick = () => {
    follower.start();
    showStopButton();
};

btnStopFollow.onclick = () => {
    follower.stop();
    showFollowButtons();
};

document.getElementById("btn-cancel").onclick = () => {
    window.close();  // closes this tab, the overview stays open
};

setMsg("Choose agent type.");
