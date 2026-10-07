// Follows one moving point like a navigation app:
//  - the map turns so the direction of travel points up
//  - the point sits below the screen centre, so you see more of what is ahead
//  - zoom depends on the road ahead: long straight road -> zoom out, turns -> zoom in
// Needs the leaflet-rotate plugin (map.setBearing).
const NAV_ZOOMS = [19, 18, 17, 16];        // zoom levels, index = "zoom mode"
const NAV_ENTER_M = [-Infinity, 856, 1719, 2997];  // zoom in when the road ahead is shorter
const NAV_EXIT_M = [1427, 2866, 4994, Infinity];   // zoom out when it is longer (hysteresis)
const NAV_TURN_ENTER_M = 51;   // a turn closer than this -> one step closer
const NAV_TURN_EXIT_M = 90;
const NAV_ZOOM_COOLDOWN_MS = 1500;

class MapFollower {
    constructor(map) {
        this.map = map;
        this.enabled = false;
        this.onUserTakeover = null;   // called when the user moves the map himself
        this.reset();

        // the user drags or zooms -> stop following, otherwise we fight over the map.
        // "dragstart" only comes from the user (panTo/flyTo don't fire it); for zoom we
        // listen to the mouse wheel and two-finger touch, because flyTo also fires "zoomstart".
        map.on("dragstart", () => this.userTookOver());
        const el = map.getContainer();
        el.addEventListener("wheel", () => this.userTookOver(), {passive: true});
        el.addEventListener("touchstart", e => {
            if (e.touches.length > 1) this.userTookOver();
        }, {passive: true});
    }

    userTookOver() {
        if (!this.enabled) return;
        this.stop();
        if (this.onUserTakeover) this.onUserTakeover();
    }

    reset() {
        this.zoomMode = 0;
        this.turnClose = false;      // "maneuver" override: one zoom step closer
        this.lastZoomChangeMs = 0;
        this.bearing = 0;            // smoothed heading in degrees
        this.lastBearingMs = 0;       // 0 -> first update turns at once
        this.zoomOld = null;         // zoom of the last flyTo
        this.flying = false;         // a flyTo animation is running
        this.pending = null;         // {center, zoom} requested while flying
    }

    start() {
        this.reset();
        this.enabled = true;
    }

    stop() {
        this.enabled = false;
        this.flying = false;
        this.pending = null;
    }

    // pos: [lat, lon]; route: list of points pos moves along; idx: segment of route pos is on
    // shortLook / longLook: how many route points to look ahead for turns / for the long road
    update(pos, route, idx, shortLook, longLook) {
        if (!this.enabled) return;
        const ahead = MapFollower.lookAhead(route, idx, shortLook, longLook);
        const zoom = this.chooseZoom(ahead.shortM, ahead.longM);
        this.follow(pos, ahead.heading, zoom);
    }

    // direction at idx and length of the route ahead (short and long look-ahead), in meters
    static lookAhead(points, idx, shortLook, longLook) {
        if (!Array.isArray(points) || points.length < 2) {
            return {heading: 0, shortM: 0, longM: 0};
        }
        const i0 = Math.max(0, Math.min(idx, points.length - 2));
        const lengthTo = (steps) => {
            const end = Math.min(points.length - 1, i0 + Math.max(1, steps));
            let m = 0;
            for (let i = i0; i < end; i++) m += haversineM(points[i], points[i + 1]);
            return m;
        };
        return {
            heading: bearingDeg(points[i0], points[i0 + 1]),
            shortM: lengthTo(shortLook),
            longM: lengthTo(longLook),
        };
    }

    chooseZoom(shortM, longM) {
        const longClamped = Math.max(50, Math.min(6500, longM));
        const now = performance.now();

        if (now - this.lastZoomChangeMs >= NAV_ZOOM_COOLDOWN_MS) {
            const prev = this.zoomMode;
            if (longClamped > NAV_EXIT_M[this.zoomMode] && this.zoomMode < NAV_ZOOMS.length - 1) {
                this.zoomMode++;
            } else if (longClamped < NAV_ENTER_M[this.zoomMode] && this.zoomMode > 0) {
                this.zoomMode--;
            }
            if (this.zoomMode !== prev) {
                this.lastZoomChangeMs = now;
                showZoomMessage(`Zoom ${NAV_ZOOMS[prev]} → ${NAV_ZOOMS[this.zoomMode]}`);
            }
        }

        if (!this.turnClose && shortM < NAV_TURN_ENTER_M) this.turnClose = true;
        else if (this.turnClose && shortM > NAV_TURN_EXIT_M) this.turnClose = false;

        const mode = this.turnClose ? Math.max(0, this.zoomMode - 1) : this.zoomMode;
        return NAV_ZOOMS[mode];
    }

    follow(pos, heading, zoom) {
        this.rotateTowards(heading);
        const center = this.centerAhead(pos, zoom, heading);

        if (this.flying) {           // keep only the newest target until the animation ends
            this.pending = {center, zoom};
            return;
        }
        const needZoom = this.zoomOld === null || Math.abs(this.map.getZoom() - zoom) > 0.5;
        if (needZoom) {
            this.flyTo(center, zoom, 1.5);
        } else {
            this.map.panTo(center, {animate: true, duration: 0.25});
        }
    }

    flyTo(center, zoom, seconds) {
        this.zoomOld = zoom;
        this.flying = true;
        this.map.once("moveend", () => this.onFlyEnd());
        this.map.flyTo(center, zoom, {animate: true, duration: seconds, easeLinearity: 0.5});
    }

    onFlyEnd() {
        this.flying = false;
        if (!this.pending || !this.enabled) return;
        const {center, zoom} = this.pending;
        this.pending = null;
        if (Math.abs(this.map.getZoom() - zoom) > 0.5) {
            this.flyTo(center, zoom, 1.2);
        } else {
            this.map.panTo(center, {animate: true, duration: 0.25});
        }
    }

    // turn the map smoothly; after ~1 s without updates it jumps to the target
    rotateTowards(heading) {
        const now = Date.now();
        const t = Math.min((now - this.lastBearingMs) / 1000, 1);
        this.lastBearingMs = now;
        const delta = (heading - this.bearing + 540) % 360 - 180;   // shortest way round
        this.bearing = (this.bearing + delta * t + 360) % 360;
        this.map.setBearing(-this.bearing);
    }

    // centre the map a bit ahead of pos, so pos is shown in the lower part of the screen
    centerAhead(pos, zoom, heading) {
        const offsetPx = {19: 200, 18: 170, 16: 120}[zoom] ?? 150;
        const p = this.map.project(pos, zoom);
        const rad = heading * Math.PI / 180;
        return this.map.unproject(L.point(p.x + Math.sin(rad) * offsetPx, p.y - Math.cos(rad) * offsetPx), zoom);
    }
}

// small fading hint at the bottom of the screen (element #zoom-msg)
function showZoomMessage(text) {
    const el = document.getElementById("zoom-msg");
    if (!el) return;
    el.textContent = text;
    el.style.opacity = "1";
    setTimeout(() => { el.style.opacity = "0.6"; }, 1200);
}
