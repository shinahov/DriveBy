let agentWS = null;
let wsReady = false;
let activeRequestId = null;


function setupAgentWS(requestId = null) {
    const url = "ws://" + window.location.host + "/ws_agent" +
        (requestId ? ("?request_id=" + encodeURIComponent(requestId)) : "");

    agentWS = new WebSocket(url);

    agentWS.onopen = () => {
        console.log("agnet ws connected");
        wsReady = true;

        if (activeRequestId && !requestId) {
            agentWS.send(JSON.stringify({
                type: "subscribe",
                request_id: activeRequestId
            }));

        }

    };
    agentWS.onclose = () => {
        console.log("agent ws disconnected");
        wsReady = false;

    };

    agentWS.onerror = (event) => {
        console.error("agent ws error:", event);
        agentWS.close();
    };

    agentWS.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        console.log("agent ws message:", msg);

        if (msg.type === "position") {
            updateMyPosition(msg.data)
        }

        if (msg.type === "routes") {
            updateMyRoutes(msg.data)
        }

        if (msg.type === "status") {
            const st = msg;

            if (st.status === "queued") {
                setMsg(`Queued.\nrequest_id=${st.request_id}`);
                return;
            }

            if (st.status === "not_matched") {
                viewMode = "agent";
                targetAgentId = st.agent_id;
                targetMatchId = null;

                setMsg(`No match.\nagent_id=${targetAgentId}`);
                return;
            }

            if (st.status === "matched") {
                viewMode = "match";
                targetMatchId = st.match_id;
                targetAgentId = st.agent_id ?? null;

                showFollowButtons();

                setMsg(`Matched.\nmatch_id=${targetMatchId}`);
                return;
            }

            // optional: subscribed etc
            console.log("unhandled status:", st.status, st);
            return;
        }

    }
}

setupAgentWS();

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

function onRouteAvailable(points) {
    map.fitBounds(points, {padding: [30, 30]});
}


// Haversine distance between two lat/lon points in meters
function haversineM(a, b) {
    const R = 6371000;
    const toRad = x => x * Math.PI / 180;
    const lat1 = toRad(a[0]), lon1 = toRad(a[1]);
    const lat2 = toRad(b[0]), lon2 = toRad(b[1]);

    const dLat = lat2 - lat1;
    const dLon = lon2 - lon1;
    const s1 = Math.sin(dLat / 2), s2 = Math.sin(dLon / 2);
    const h = s1 * s1 + Math.cos(lat1) * Math.cos(lat2) * s2 * s2;
    return 2 * R * Math.asin(Math.sqrt(h));
}


// Bearing between two lat/lon points in degrees
function bearingDeg(a, b) {
    const [lat1, lon1] = a.map(x => x * Math.PI / 180);
    const [lat2, lon2] = b.map(x => x * Math.PI / 180);

    const dLon = lon2 - lon1;
    const y = Math.sin(dLon) * Math.cos(lat2);
    const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
    let brng = Math.atan2(y, x) * 180 / Math.PI;   // -180..180
    brng = (brng + 360) % 360;                     // 0..360
    return brng;
}


function lerpAngle(a, b, t) {
    let delta = (b - a + 540) % 360 - 180;
    return (a + delta * t + 360) % 360;
}


// Smoothly set bearing
function setSmoothBearing(targetBearing) {
    const now = Date.now();
    const dt = (now - lastBearingUpdateTime) / 1000; // seconds
    lastBearingUpdateTime = now;

    const t = Math.min(dt, 1); // smoothing factor
    smoothBearing = lerpAngle(smoothBearing, targetBearing, t);
    map.setBearing(-smoothBearing);
}

let flying = false;
let pendingCenter = null;
let pendingZoom = null;

let desiredZoom = null;
let flyToCalls = 0;


function offsetBySegLen(zoom) {
    const table = {
        20: 220,
        19: 200,
        18: 170,
        16: 120
    };
    return table[zoom] ?? 150;
}


function offsetCenterByHeading(latlng, zoom, headingDeg, offsetPx) {
    // latlng to pixel at zoom
    const p = map.project(latlng, zoom);

    // Heading
    const rad = headingDeg * Math.PI / 180;

    // In screen/world pixel coords:
    // x grows right, y grows down
    const dx = Math.sin(rad) * offsetPx;
    const dy = -Math.cos(rad) * offsetPx;    // minus because y down

    const p2 = L.point(p.x + dx, p.y + dy);

    // back to latlng
    return map.unproject(p2, zoom);
}


function onFlyFinished() {
    flying = false;

    // Apply last pending request once (latest-wins)
    if (pendingCenter || pendingZoom !== null) {
        const c = pendingCenter || map.getCenter();
        const z = (pendingZoom !== null) ? pendingZoom : map.getZoom();

        pendingCenter = null;
        pendingZoom = null;

        // Re-enter follow logic once with latest target
        // (we call flyTo/panTo exactly once)
        const curZ = map.getZoom();
        const needZoom = Math.abs(curZ - z) > 0.5;

        if (needZoom) {
            flyToCalls++;
            console.log("[FOLLOW] flyTo (pending)", {flyToCalls, z, curZ});

            zoomOld = z;
            flying = true;
            map.once("moveend", onFlyFinished);

            map.flyTo(c, z, {
                animate: true,
                duration: 1.2,
                easeLinearity: 0.5
            });
        } else {
            // just pan after fly finished
            map.panTo(c, {animate: true, duration: 0.25});
        }
    }
}


function followWithRotation(centerLatLng, heading, zoom, segLenM) {
    if (!followEnabled) return;
    lastFollowTick = Date.now();

    desiredZoom = zoom;

    const currentMapZoom = map.getZoom();

    console.log("[FOLLOW] tick", {
        desiredZoom: zoom,
        currentMapZoom,
        zoomOld,
        flying
    });

    setSmoothBearing(heading);

    const offsetPx = offsetBySegLen(zoom);
    const centerLatLngOffset = offsetCenterByHeading(centerLatLng, zoom, heading, offsetPx);

    // If a fly is running, store the latest request and exit
    if (flying) {
        pendingCenter = centerLatLngOffset;
        pendingZoom = zoom;
        return;
    }

    const needZoom = (zoomOld === null) || (Math.abs(currentMapZoom - zoom) > 0.5);

    if (needZoom) {
        flyToCalls++;
        console.log("[FOLLOW] flyTo", {flyToCalls, zoom, zoomOld, currentMapZoom});

        zoomOld = zoom;
        flying = true;

        // Ensure we always end flying
        map.once("moveend", onFlyFinished);

        map.flyTo(centerLatLngOffset, zoom, {
            animate: true,
            duration: 1.5,
            easeLinearity: 0.5
        });
        return;
    }

    // Normal follow: pan only
    pendingCenter = null;
    pendingZoom = null;

    map.panTo(centerLatLngOffset, {animate: true, duration: 0.25});
}

map.on("zoomend", () => {
    console.log("[MAP] zoomend real=", map.getZoom(), "desired=", desiredZoom);
});


// Get heading and length of segment starting at points[idx]
function headingAndSegLens(points, idx, shortLook = 8, longLook = 50) {
    if (!Array.isArray(points) || points.length < 2) {  // the bug (segLongM was 0 first few kilometers) is disappeared after adding logging (???)
        console.warn("[headingAndSegLens] invalid points", {
            isArray: Array.isArray(points),
            len: points?.length,
            idx
        });

        return {
            heading: 0,
            segShortM: 0,
            segLongM: 0
        };
    }

    const i0 = Math.max(0, Math.min(idx, points.length - 2));

    // short lookahead (local / maneuver)
    const iShort = Math.min(points.length - 1, i0 + Math.max(1, shortLook));
    let segShortM = 0;
    for (let i = i0; i < iShort; i++) {
        segShortM += haversineM(points[i], points[i + 1]);
    }

    // long lookahead (global / context)
    const iLong = Math.min(points.length - 1, i0 + Math.max(1, longLook));
    let segLongM = 0;
    for (let i = i0; i < iLong; i++) {
        segLongM += haversineM(points[i], points[i + 1]);
    }

    // Heading always from immediate direction (stable + responsive)
    const heading = bearingDeg(points[i0], points[Math.min(i0 + 1, points.length - 1)]);

    return {
        heading,      // direction of travel
        segShortM,    // short / local segment length (maneuver)
        segLongM      // long / global segment length (context)
    };
}


// Needs: map maxZoom >= 22 (tile layer must support it)

let lastZoomChangeMs = 0;


function logZoomMessage(text) {
    const el = document.getElementById("zoom-msg");
    if (!el) return;

    el.textContent = text;
    el.style.opacity = "1";

    // auto-fade
    setTimeout(() => {
        el.style.opacity = "0.6";
    }, 1200);
}

function updateZoomModeDual(segShortM, segLongM) {
    const dL = Math.max(50, Math.min(6500, segLongM));
    const dS = segShortM;

    const ZOOMS = [19, 18, 17, 16];

    // thresholds based on LONG (stable)
    const ENTER_L = [-Infinity, 856, 1719, 2997];
    const EXIT_L = [1427, 2866, 4994, Infinity];

    // maneuver override based on SHORT (only zoom IN)
    const MANEUVER_ENTER = 51;  // if short is very small zoom in one step
    const MANEUVER_EXIT = 90;  // release override when short is larger again

    const now = (typeof performance !== "undefined" ? performance.now() : Date.now());
    const COOLDOWN_MS = 1500;

    // base update from LONG with hysteresis
    if (now - lastZoomChangeMs >= COOLDOWN_MS) {
        const prev = zoomMode;

        if (dL > EXIT_L[zoomMode] && zoomMode < ZOOMS.length - 1)
            zoomMode++; // zoom OUT
        else if (dL < ENTER_L[zoomMode] && zoomMode > 0)
            zoomMode--; // zoom IN

        if (zoomMode !== prev) {
            lastZoomChangeMs = now;
            logZoomMessage(`Zoom ${ZOOMS[prev]} → ${ZOOMS[zoomMode]} | long ${segLongM.toFixed(1)} m`);
        }
    }

    // maneuver override: allow only zoom IN (more detailed)
    // store a separate flag for override
    if (typeof updateZoomModeDual.maneuver === "undefined") updateZoomModeDual.maneuver = false;

    if (!updateZoomModeDual.maneuver && dS < MANEUVER_ENTER) {
        updateZoomModeDual.maneuver = true;
    } else if (updateZoomModeDual.maneuver && dS > MANEUVER_EXIT) {
        updateZoomModeDual.maneuver = false;
    }

    let effectiveMode = zoomMode;

    if (updateZoomModeDual.maneuver) {
        // zoom in by 1 step, but not beyond mode 0
        effectiveMode = Math.max(0, zoomMode - 1);
    }

    return ZOOMS[effectiveMode];
}


function zoomFromSegLen(segShortM, segLongM) {
    return updateZoomModeDual(segShortM, segLongM);
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

// Navigation variables
let followEnabled = false;
let lastUserInteractionTime = 0;
let smoothBearing = 0;
let lastBearingUpdateTime = 0;
let zoomMode = 2;


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
    const res = await fetch(
        url + "?ts=" + Date.now(),
        {cache: "no-store"});
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


async function updateMyPosition(data) {
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
                const {heading, segShortM, segLongM} =
                    headingAndSegLens(walkerRoutePoints, myWalkerPIdx, 5, 30);
                const zoom = zoomFromSegLen(segShortM, segLongM);
                followWithRotation(latlng, heading, zoom, segShortM);
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
                const {heading, segShortM, segLongM} =
                    headingAndSegLens(driverRoutePoints, myDriverIdx, 20, 60);
                const zoom = zoomFromSegLen(segShortM, segLongM);
                followWithRotation(latlng, heading, zoom, segShortM);
            }
        }

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


// routes are only meaningful once a match exists; unmatched agent has no match route.
function sliceInclusive(points, a, b) {
    if (a < 0) a = 0;
    if (b >= points.length) b = points.length - 1;
    if (b < a) return [];
    return points.slice(a, b + 1);
}

async function updateMyRoutes(data) {
    if (viewMode !== "match") return;


    const routes = Array.isArray(data.routes) ? data.routes : [];
    const r = routes.find(x => String(x.match_id) === String(targetMatchId));
    if (!r) return;

    const d = r.driver_route?.geometry_latlon;
    const w1 = r.walk_to_pickup?.geometry_latlon;
    const w2 = r.walk_from_dropoff?.geometry_latlon;
    const pickup = r.points?.pickup;
    const dropoff = r.points?.dropoff;
    if (!Array.isArray(d) || !Array.isArray(w1) || !Array.isArray(w2)) return;
    if (!Array.isArray(pickup) || !Array.isArray(dropoff)) return;
    driverRoutePoints = d;
    walkerRoutePoints = w1.concat(w2);


    if (!Array.isArray(d) ||
        !Array.isArray(w1) ||
        !Array.isArray(w2) ||
        !pickup || !dropoff) return;

    const iPick = r.idx?.pickup;
    const iDrop = r.idx?.dropoff;
    if (!Number.isInteger(iPick) ||
        !Number.isInteger(iDrop)) return;

    const a = Math.min(iPick, iDrop);
    const b = Math.max(iPick, iDrop);

    const dIdx =
        Number.isInteger(myDriverIdx) ? myDriverIdx : 0; // i dont why ist only works if i do this
    const walkerpickIdx =
        Number.isInteger(myWalkerPIdx) ? myWalkerPIdx : 0;
    const walkerdropIdx =
        Number.isInteger(myWalkerDIdx) ? myWalkerDIdx : 0;

    const segPre = sliceInclusive(d, dIdx, a);
    const segRide = sliceInclusive(d, Math.max(dIdx, a), b);
    const segPost = sliceInclusive(d, Math.max(dIdx, b), d.length - 1);
    const segWalkToPickup = sliceInclusive(
        w1, walkerpickIdx, w1.length - 1);
    const segWalkFromDropoff = sliceInclusive(
        w2, Math.max(walkerdropIdx, 0), w2.length - 1);

    const all = d.concat(w1, w2);

    // Observe state BEFORE removing (important)
    const hadRouteBefore = !!myRouteRide;

    // Remove old layers
    myRoutePre = removeIfExists(myRoutePre);
    myRouteRide = removeIfExists(myRouteRide);
    myRoutePost = removeIfExists(myRoutePost);
    myWalkToPickup = removeIfExists(myWalkToPickup);
    myWalkFromDropoff = removeIfExists(myWalkFromDropoff);
    //myPickup = removeIfExists(myPickup);
    //myDropoff = removeIfExists(myDropoff);
    clearPreview();

    // Draw new layers
    myRoutePre = L.polyline(segPre, {weight: 5, opacity: 0.8})
        .addTo(map).bindTooltip("Driver pre");
    myRouteRide = L.polyline(segRide, {weight: 6, opacity: 0.9, color: "red"})
        .addTo(map).bindTooltip("Driver ride");
    myRoutePost = L.polyline(segPost, {weight: 5, opacity: 0.8})
        .addTo(map).bindTooltip("Driver post");

    myWalkToPickup = L.polyline(segWalkToPickup,
        {weight: 4, opacity: 0.85, dashArray: "6", color: "green"})
        .addTo(map).bindTooltip("Walk to pickup");
    myWalkFromDropoff = L.polyline(segWalkFromDropoff,
        {weight: 4, opacity: 0.85, dashArray: "6", color: "green"})
        .addTo(map).bindTooltip("Walk from dropoff");

    if (!myPickup) {
        myPickup = L.marker(pickup, {icon: pickDropIcon}).addTo(map).bindTooltip("Pickup");
    } else {
        myPickup.setLatLng(pickup);
    }

    if (!myDropoff) {
        myDropoff = L.marker(dropoff, {icon: pickDropIcon}).addTo(map).bindTooltip("Dropoff");
    } else {
        myDropoff.setLatLng(dropoff);
    }


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

        if (!wsReady) {
            setupAgentWS();
        }

        if (!wsReady) {
            setMsg("WS not connected yet.");
            return;
        }

        createdKind = kind;
        agentWS.send(JSON.stringify({type: "create_request", payload}));


    } catch (e) {
        // On error, re-enable selection so the user can try again.
        btnWalker.disabled = false;
        btnDriver.disabled = false;
        btnConfirm.disabled = (!(step === "pick_start" || step === "pick_dest"));
        btnCreate.disabled = (step !== "ready");

        setMsg(`Create failed:\n${e.message}`);
    }
};

btnFollow.onclick = () => {
    followEnabled = true;
    lastUserInteractionTime = Date.now();
    zoomOld = null;
    flying = false;
    pendingCenter = null;
    pendingZoom = null;
    lastZoomChangeMs = 0;
    zoomMode = 0;

    showStopButton();
};

btnStopFollow.onclick = () => {
    followEnabled = false;
    flying = false;
    pendingCenter = null;
    pendingZoom = null;

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


// dont work since leaflet cannot distinguish programmatic vs user-initiated events
map.on("dragstart", (e) => {
    if (!e?.originalEvent) return;       // ignore programmatic
    followEnabled = false;
    lastUserInteractionTime = Date.now();
    console.log("[FOLLOW] OFF by USER drag");
});

map.on("zoomstart", (e) => {
    if (!e?.originalEvent) return;       // ignore programmatic
    followEnabled = false;
    lastUserInteractionTime = Date.now();
    console.log("[FOLLOW] OFF by USER zoom");
});


let lastFollowTick = 0;

setInterval(() => {
    console.log("[WD]", {
        followEnabled,
        flying,
        zoom: map.getZoom(),
        hasPending: !!pendingCenter || pendingZoom !== null,
        secondsSinceTick: ((Date.now() - lastFollowTick) / 1000).toFixed(1)
    });
}, 2000);


//  Init

viewMode = "create";
resetCreateState();
setMsg("Choose agent type.");
