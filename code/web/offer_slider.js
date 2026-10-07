// "Slide to accept" like the iPhone call screen: drag the green knob onto the
// partner's photo at the right end. In the middle: "Accept match with <name>" + score.
//   onAccept(): called once the knob reached the end
const OFFER_ACCEPT_AT = 0.9;   // released after 90 % of the way -> accepted, else it slides back

class OfferSlider {
    constructor({onAccept}) {
        this.onAccept = onAccept;
        this.box = document.getElementById("offer");
        this.track = document.getElementById("offer-track");
        this.knob = document.getElementById("offer-knob");
        this.text = document.getElementById("offer-text");
        this.photo = document.getElementById("offer-photo");
        this.name = document.getElementById("offer-name");
        this.score = document.getElementById("offer-score");

        this.dragging = false;
        this.startX = 0;      // pointer x minus knob offset when the drag started
        this.offset = 0;      // how far the knob is moved to the right (px)

        this.knob.addEventListener("pointerdown", e => this.start(e));
        window.addEventListener("pointermove", e => this.move(e));
        window.addEventListener("pointerup", () => this.end());
        window.addEventListener("pointercancel", () => this.end());
    }

    // partner: {name, photo, rating, trips}
    show({name, photo, rating, trips}) {
        this.name.textContent = name;
        this.photo.src = photo;
        this.score.textContent = `\u2605 ${rating.toFixed(1)} \u00b7 ${trips} trips`;
        this.box.hidden = false;
        this.setOffset(0);
    }

    hide() {
        this.box.hidden = true;
        this.dragging = false;
    }

    isShown() {
        return !this.box.hidden;
    }

    // the knob can move from the left end to the right end of the track
    maxOffset() {
        const padding = 6;
        return Math.max(1, this.track.clientWidth - this.knob.offsetWidth - 2 * padding);
    }

    start(e) {
        this.dragging = true;
        this.startX = e.clientX - this.offset;
        this.knob.style.transition = "none";
        if (this.knob.setPointerCapture) this.knob.setPointerCapture(e.pointerId);
        e.preventDefault();  // no text selection, no map drag
    }

    move(e) {
        if (!this.dragging) return;
        this.setOffset(Math.min(this.maxOffset(), Math.max(0, e.clientX - this.startX)));
    }

    end() {
        if (!this.dragging) return;
        this.dragging = false;
        this.knob.style.transition = "transform 0.25s ease";
        if (this.offset >= OFFER_ACCEPT_AT * this.maxOffset()) {
            this.setOffset(this.maxOffset());
            this.onAccept();
        } else {
            this.setOffset(0);   // not far enough: slide back
        }
    }

    setOffset(px) {
        this.offset = px;
        this.knob.style.transform = `translateX(${px}px)`;
        this.text.style.opacity = String(1 - px / this.maxOffset());   // text fades while sliding
    }
}
