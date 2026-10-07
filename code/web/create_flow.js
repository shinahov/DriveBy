// The "create an agent" part of the page:
//   top:    KindPicker - icon of the agent type (walker / car), tap to switch
//   bottom: tap START and DEST on the map (each confirmed with "Confirm"), then "Create"
//   isActive(): false once the agent exists -> taps are ignored
//   setMsg(text): shows a message in the bottom panel
//   onCreate(payload): sends the request, returns false if that failed
const destIcon = L.icon({
    iconUrl: "icons/dest.png",
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    tooltipAnchor: [0, -12]
});

const KIND_ICONS = {walker: "icons/walker.png", driver: "icons/car.png"};

// Round button at the top that shows the current agent type. Tap it -> both types
// appear, the selected one is blue. Tap a type to select it, tap anywhere else to close.
class KindPicker {
    constructor(onChange) {
        this.onChange = onChange;
        this.value = "walker";
        this.button = document.getElementById("kind-btn");
        this.icon = document.getElementById("kind-icon");
        this.menu = document.getElementById("kind-menu");
        this.options = {
            walker: document.getElementById("kind-walker"),
            driver: document.getElementById("kind-driver"),
        };

        this.button.onclick = e => {
            e.stopPropagation();  // otherwise the document click below closes it again
            this.toggle();
        };
        for (const [kind, el] of Object.entries(this.options)) {
            el.onclick = e => {
                e.stopPropagation();
                this.select(kind);
            };
        }
        document.addEventListener("click", () => this.close());
        this.render();
    }

    isOpen() {
        return !this.menu.hidden;
    }

    toggle() {
        if (this.button.disabled) return;
        this.menu.hidden = !this.menu.hidden;
    }

    close() {
        this.menu.hidden = true;
    }

    select(kind) {
        this.value = kind;
        this.render();
        this.onChange(kind);
    }

    setEnabled(enabled) {
        this.button.disabled = !enabled;
        if (!enabled) this.close();
    }

    render() {
        this.icon.src = KIND_ICONS[this.value];
        for (const [kind, el] of Object.entries(this.options)) {
            el.classList.toggle("selected", kind === this.value);
        }
    }
}

class CreateFlow {
    constructor(map, {isActive, setMsg, onCreate}) {
        this.map = map;
        this.isActive = isActive;
        this.setMsg = setMsg;
        this.onCreate = onCreate;

        this.kindPicker = new KindPicker(kind => this.setKind(kind));
        this.btn = {
            confirm: document.getElementById("btn-confirm"),
            create: document.getElementById("btn-create"),
        };
        this.btn.confirm.onclick = () => this.confirm();
        this.btn.create.onclick = () => this.create();
        map.on("click", ev => this.onMapClick([ev.latlng.lat, ev.latlng.lng]));

        this.startMarker = null;
        this.destMarker = null;
        this.previewLine = null;
        this.reset();
    }

    reset() {
        this.kind = this.kindPicker.value;   // "walker" | "driver"
        this.step = "pick_start";            // pick_start | pick_dest | ready
        this.pendingPoint = null;    // clicked but not confirmed yet
        this.startPoint = null;
        this.destPoint = null;
        this.btn.confirm.disabled = true;
        this.btn.create.disabled = true;
        this.removeLayer("startMarker");
        this.removeLayer("destMarker");
        this.clearPreview();
    }

    // the type can be changed at any time before "Create"; chosen points stay
    setKind(kind) {
        if (!this.isActive()) return;
        this.kind = kind;
        this.showHint();
    }

    // what to do next, shown in the bottom panel
    showHint() {
        const who = this.kind === "driver" ? "Driver" : "Walker";
        const hints = {
            pick_start: "Tap the map to set START.",
            pick_dest: "Tap the map to set DEST.",
            ready: "Tap Create.",
        };
        const next = this.pendingPoint ? "Tap Confirm (or tap elsewhere to move it)." : hints[this.step];
        this.setMsg(`${who}: ${next}`);
    }

    onMapClick(point) {
        if (this.kindPicker.isOpen()) {  // this tap only closes the type menu
            this.kindPicker.close();
            return;
        }
        if (!this.isActive()) return;
        if (this.step !== "pick_start" && this.step !== "pick_dest") return;

        this.pendingPoint = point;
        this.btn.confirm.disabled = false;

        if (this.step === "pick_start") {
            this.placeMarker("startMarker", point,
                () => L.circleMarker(point, {radius: 7, weight: 2, fillOpacity: 1}), "START");
        } else {
            this.placeMarker("destMarker", point, () => L.marker(point, {icon: destIcon}), "DEST");
        }
        this.showHint();
        this.redrawPreview();
    }

    confirm() {
        if (!this.isActive() || !this.pendingPoint) return;

        if (this.step === "pick_start") {
            this.startPoint = this.pendingPoint;
            this.step = "pick_dest";
        } else if (this.step === "pick_dest") {
            this.destPoint = this.pendingPoint;
            this.step = "ready";
            this.btn.create.disabled = false;
        }
        this.pendingPoint = null;
        this.btn.confirm.disabled = true;
        this.showHint();
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
        this.kindPicker.setEnabled(false);
    }

    unlock() {
        this.kindPicker.setEnabled(true);
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
