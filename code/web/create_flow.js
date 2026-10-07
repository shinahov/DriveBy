// The "create an agent" panel: choose walker or driver, click START and DEST
// on the map (each confirmed with "Confirm"), then "Create".
//   isActive(): false once the agent exists -> clicks are ignored
//   setMsg(text): shows a message in the panel
//   onCreate(payload): sends the request, returns false if that failed
const destIcon = L.icon({
    iconUrl: "icons/dest.png",
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    tooltipAnchor: [0, -12]
});

class CreateFlow {
    constructor(map, {isActive, setMsg, onCreate}) {
        this.map = map;
        this.isActive = isActive;
        this.setMsg = setMsg;
        this.onCreate = onCreate;

        this.btn = {
            walker: document.getElementById("btn-kind-walker"),
            driver: document.getElementById("btn-kind-driver"),
            confirm: document.getElementById("btn-confirm"),
            create: document.getElementById("btn-create"),
        };
        this.btn.walker.onclick = () => this.chooseKind("walker");
        this.btn.driver.onclick = () => this.chooseKind("driver");
        this.btn.confirm.onclick = () => this.confirm();
        this.btn.create.onclick = () => this.create();
        map.on("click", ev => this.onMapClick([ev.latlng.lat, ev.latlng.lng]));

        this.startMarker = null;
        this.destMarker = null;
        this.previewLine = null;
        this.reset();
    }

    reset() {
        this.kind = null;            // "walker" | "driver"
        this.step = "choose_kind";   // choose_kind | pick_start | pick_dest | ready
        this.pendingPoint = null;    // clicked but not confirmed yet
        this.startPoint = null;
        this.destPoint = null;
        this.btn.confirm.disabled = true;
        this.btn.create.disabled = true;
        this.removeLayer("startMarker");
        this.removeLayer("destMarker");
        this.clearPreview();
    }

    chooseKind(kind) {
        if (!this.isActive()) return;
        this.kind = kind;
        this.step = "pick_start";
        this.pendingPoint = null;
        this.btn.confirm.disabled = true;
        this.btn.create.disabled = true;
        this.setMsg(`${kind}: click map to select START, then Confirm.`);
    }

    onMapClick(point) {
        if (!this.isActive()) return;
        if (this.step !== "pick_start" && this.step !== "pick_dest") return;

        this.pendingPoint = point;
        this.btn.confirm.disabled = false;

        if (this.step === "pick_start") {
            this.placeMarker("startMarker", point,
                () => L.circleMarker(point, {radius: 7, weight: 2, fillOpacity: 1}), "START");
            this.setMsg(`${this.kind}: START = ${fmtPoint(point)}\nClick Confirm to set START.`);
        } else {
            this.placeMarker("destMarker", point, () => L.marker(point, {icon: destIcon}), "DEST");
            this.setMsg(`${this.kind}: DEST = ${fmtPoint(point)}\nClick Confirm to set DEST.`);
        }
        this.redrawPreview();
    }

    confirm() {
        if (!this.isActive() || !this.pendingPoint) return;

        if (this.step === "pick_start") {
            this.startPoint = this.pendingPoint;
            this.step = "pick_dest";
            this.setMsg(`${this.kind}: START = ${fmtPoint(this.startPoint)}\nNow click map to select DEST, then Confirm.`);
        } else if (this.step === "pick_dest") {
            this.destPoint = this.pendingPoint;
            this.step = "ready";
            this.btn.create.disabled = false;
            this.setMsg(`${this.kind}: DEST = ${fmtPoint(this.destPoint)}\nClick Create.`);
        }
        this.pendingPoint = null;
        this.btn.confirm.disabled = true;
        this.redrawPreview();
    }

    create() {
        if (!this.isActive() || this.step !== "ready") return;
        this.lock();  // prevent double-submit
        this.setMsg("Sending create request...");
        const payload = {
            type: this.kind,
            start: {lat: this.startPoint[0], lon: this.startPoint[1]},
            dest: {lat: this.destPoint[0], lon: this.destPoint[1]},
        };
        if (!this.onCreate(payload)) {
            this.setMsg("Not connected to the server yet. Try again in a moment.");
            this.unlock();
            return;
        }
        this.clearPreview();  // the agent exists now: keep only the START and DEST markers
    }

    lock() {
        Object.values(this.btn).forEach(b => { b.disabled = true; });
    }

    unlock() {
        this.btn.walker.disabled = false;
        this.btn.driver.disabled = false;
        this.btn.confirm.disabled = !(this.step === "pick_start" || this.step === "pick_dest");
        this.btn.create.disabled = (this.step !== "ready");
        this.redrawPreview();  // e.g. after an error: show the planned line again
    }

    // dashed line from START to the (pending) DEST
    redrawPreview() {
        this.clearPreview();
        const a = this.startPoint;
        const b = this.pendingPoint || this.destPoint;
        if (a && b) {
            this.previewLine = L.polyline([a, b], {weight: 3, dashArray: "6,6"}).addTo(this.map);
        }
    }

    clearPreview() {
        this.removeLayer("previewLine");
    }

    placeMarker(name, point, create, tooltip) {
        if (this[name]) this[name].setLatLng(point);
        else this[name] = create().addTo(this.map).bindTooltip(tooltip);
    }

    removeLayer(name) {
        if (this[name]) this.map.removeLayer(this[name]);
        this[name] = null;
    }
}

function fmtPoint(p) {
    return `${p[0].toFixed(6)}, ${p[1].toFixed(6)}`;
}
