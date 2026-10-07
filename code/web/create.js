// Page for ONE user: create a walker or driver, then watch it (and its match).
// Parts: CreateFlow (create_flow.js) picks start/dest, MatchLayers (match_layers.js)
// draws the match, MapFollower (navigation.js) follows the agent.

// ---------- map ----------
const map = L.map("map", {rotate: true, bearing: 0, rotateControl: false, zoomControl: false});

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
const sheet = document.getElementById("sheet");
const cancelBox = document.getElementById("cancel-box");
const cancelLabel = document.getElementById("cancel-label");
const btnFollow = document.getElementById("btn-follow");
const btnStopFollow = document.getElementById("btn-stop-follow");

function setMsg(text) {
    msgEl.textContent = text;
}

// while a trip runs only the map, the red X and "Navigate" are shown
function showTripControls(onTrip) {
    sheet.hidden = onTrip;
    cancelBox.hidden = !onTrip;
    cancelLabel.textContent = "Cancel trip";
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
let viewMode = "create";   // create -> agent (waiting) -> match -> back to create when done
let myRequestId = null;    // request_id of my agent (null until the server queued it)
let createdKind = null;    // "walker" | "driver"
let targetMatchId = null;
let targetAgentId = null;

// what is drawn for my agent
let myWalkerMarker = null;
let myDriverMarker = null;
let myLeftoverMarker = null;
let myMatch = null;        // MatchLayers of my match
let myFrame = null;        // newest position frame of my match (phase + progress)

// match offer at the bottom: slide to accept (offer_slider.js)
const offer = new OfferSlider({onAccept: acceptMatch});

// dummy partner until the server sends real names and photos
const DUMMY_PARTNER = {
    walker: {name: "Max", photo: "icons/avatar.svg", rating: 4.8, trips: 23},   // a walker is offered a driver
    driver: {name: "Anna", photo: "icons/avatar.svg", rating: 4.6, trips: 9},   // a driver is offered a walker
};

const follower = new MapFollower(map);
follower.onUserTakeover = showFollowButtons;  // user moved the map -> offer "Navigate" again

const createFlow = new CreateFlow(map, {
    isActive: () => viewMode === "create",
    setMsg,
    onCreate: payload => {
        createdKind = payload.type;
        return socket.send({type: "create_request", payload});
    },
});

// ---------- remember my agent across page reloads (per browser tab) ----------
const STORAGE_KEY = "driveby.myAgent";

function saveMyAgent() {
    try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify({requestId: myRequestId, kind: createdKind}));
    } catch (e) { /* storage blocked: reload just starts over */ }
}

function forgetMyAgent() {
    try {
        sessionStorage.removeItem(STORAGE_KEY);
    } catch (e) { /* ignore */ }
}

function loadMyAgent() {
    try {
        return JSON.parse(sessionStorage.getItem(STORAGE_KEY));
    } catch (e) {
        return null;
    }
}

// ---------- connection: what to do with each message type ----------
const socket = new LiveSocket("/ws_agent")
    .on("position", msg => updateMatchPosition(msg.data.frame))
    .on("agent_position", msg => updateAgentPosition(msg.data))
    .on("routes", msg => updateMyRoutes(msg.data))
    .on("status", msg => handleStatus(msg));

// after a reconnect the server no longer knows us -> subscribe again
socket.onConnect = () => {
    if (myRequestId) socket.send({type: "subscribe", request_id: myRequestId});
};

function handleStatus(st) {
    if (st.status === Status.QUEUED) {
        myRequestId = st.request_id;
        saveMyAgent();
        if (viewMode === "create") viewMode = "agent";
        showTripControls(true);
        setMsg(`Queued.\nrequest_id=${st.request_id}`);
        return;
    }

    if (st.status === Status.NOT_MATCHED) {
        // also sent to a driver whose passenger got off: back to waiting
        leaveMatch();
        viewMode = "agent";
        targetAgentId = st.agent_id;
        targetMatchId = null;
        setMsg(`No match.\nagent_id=${targetAgentId}`);
        return;
    }

    if (st.status === Status.MATCHED) {
        clearMyViewLayers();  // the "waiting" dot
        viewMode = "match";
        targetMatchId = st.match_id;
        targetAgentId = st.agent_id ?? null;
        showOffer();
        setMsg(`Matched.\nmatch_id=${targetMatchId}`);
        return;
    }

    if (st.status === Status.SUBSCRIBED) return;

    if (st.status === Status.DONE) {
        backToCreate("Arrived. Trip finished.\nYou can create a new agent.");
        return;
    }

    if (st.status === Status.CANCELLED) {
        backToCreate("Trip cancelled.\nYou can create a new agent.");
        return;
    }

    if (st.status === Status.UNKNOWN) {
        // the server does not know my agent any more (e.g. it was restarted)
        backToCreate("Your previous agent is gone (server restarted?).\nCreate a new one.");
        return;
    }

    if (st.status === Status.ERROR) {
        // the agent could not be created -> keep the chosen points, let the user try again
        backToCreate(`Error:\n${st.message}`, {keepPoints: true});
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
    myFrame = null;
    if (myMatch) myMatch.remove();
    myMatch = null;
}

// a match was found: show the partner and the "slide to accept" slider
function showOffer() {
    btnFollow.hidden = true;
    btnStopFollow.hidden = true;
    offer.show(DUMMY_PARTNER[createdKind] || DUMMY_PARTNER.walker);
    document.body.classList.add("offer-open");
}

function hideOffer() {
    offer.hide();
    document.body.classList.remove("offer-open");
}

// slid to the end. For now only on this page; the server does not wait for it yet.
function acceptMatch() {
    hideOffer();
    showFollowButtons();
}

// the trip is over (or never started): show the create panel again
function backToCreate(message, {keepPoints = false} = {}) {
    leaveMatch();
    forgetMyAgent();
    myRequestId = null;
    viewMode = "create";
    if (!keepPoints) createFlow.reset();
    createFlow.unlock();
    showTripControls(false);
    setMsg(message);
}

// stop showing / following the match (it is over)
function leaveMatch() {
    hideOffer();
    clearMyViewLayers();
    follower.stop();
    btnFollow.hidden = true;
    btnStopFollow.hidden = true;
}

// create the marker the first time, move it afterwards
function placeMarker(marker, latlng, makeMarker) {
    if (marker) return marker.setLatLng(latlng);
    return makeMarker(latlng).addTo(map);
}

// both agents of my match (frame = one entry of the server's position message)
function updateMatchPosition(frame) {
    if (viewMode !== "match" || !frame) return;
    if (targetMatchId == null && frame.sim_id != null) targetMatchId = frame.sim_id;
    if (String(frame.sim_id) !== String(targetMatchId)) return;
    myFrame = frame;

    const walkerPos = [frame.walker.lat, frame.walker.lon];
    const driverPos = [frame.driver.lat, frame.driver.lon];
    myWalkerMarker = placeMarker(myWalkerMarker, walkerPos,
        p => L.marker(p, {icon: walkerIcon}).bindTooltip("Walker (match)"));
    myDriverMarker = placeMarker(myDriverMarker, driverPos,
        p => L.marker(p, {icon: driverIcon}).bindTooltip("Driver (match)"));

    const leg = myLeg(frame);
    if (leg) follower.update(createdKind === "walker" ? walkerPos : driverPos,
        leg.route, leg.idx, leg.shortLook, leg.longLook);

    updateMyProgress();
}

// the route my agent moves along right now, and where on it
function myLeg(frame) {
    if (!myMatch) return null;
    const onFoot = (route, idx) => ({route, idx, shortLook: 5, longLook: 30});
    const inCar = {route: myMatch.driver, idx: frame.driver.idx, shortLook: 20, longLook: 60};

    if (createdKind === "driver") return inCar;
    switch (frame.phase) {
        case Phase.WALK_TO_PICKUP:
            return onFoot(myMatch.walkTo, frame.walker.pIdx);
        case Phase.WAIT_AT_PICKUP:
            return onFoot(myMatch.walkTo, myMatch.walkTo.length - 2);
        case Phase.RIDE_WITH_DRIVER:
            return inCar;
        case Phase.WALK_FROM_DROPOFF:
            return onFoot(myMatch.walkFrom, frame.walker.dIdx);
        default:
            return null;
    }
}

// my agent while it waits for a match (the server sends "agent_position" only then)
function updateAgentPosition(a) {
    if (viewMode !== "agent" || String(a.agent_id) !== String(targetAgentId)) return;

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
    createFlow.clearPreview();

    if (firstTime) map.fitBounds(myMatch.allPoints(), {padding: [30, 30]});
}

// hide the parts of my match route that are already done
function updateMyProgress() {
    if (!myMatch || !myFrame) return;
    const phase = myFrame.phase;
    const walkToDone = phase !== Phase.WALK_TO_PICKUP;
    const walkFromStarted = phase === Phase.WALK_FROM_DROPOFF || phase === Phase.DONE;
    myMatch.setProgress({
        driverIdx: myFrame.driver.idx,
        walkToIdx: walkToDone ? myMatch.walkTo.length : myFrame.walker.pIdx,
        walkFromIdx: !walkFromStarted ? 0
            : (phase === Phase.DONE ? myMatch.walkFrom.length : myFrame.walker.dIdx),
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

// red X: cancel the trip (the server answers with "cancelled")
document.getElementById("btn-cancel-trip").onclick = () => {
    if (!myRequestId) return;
    if (!socket.send({type: "cancel", request_id: myRequestId})) {
        cancelLabel.textContent = "Not connected";
    }
};

document.getElementById("btn-cancel").onclick = () => {
    window.close();  // closes this tab, the overview stays open
};

// ---------- start ----------
const saved = loadMyAgent();
if (saved && saved.requestId) {
    // page was reloaded: the subscribe in socket.onConnect brings back the state
    myRequestId = saved.requestId;
    createdKind = saved.kind;
    viewMode = "agent";
    createFlow.lock();
    showTripControls(true);
    setMsg("Reconnecting to your agent...");
} else {
    showTripControls(false);
    createFlow.showHint();
}
