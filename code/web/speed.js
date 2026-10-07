// Simulation speed = simulated seconds per tick. The server ticks every 0.05 s
// (TICK_SLEEP_S in config.py), so speed 0.05 is real time.
// The slider is exponential: small steps at the slow end, big steps at the fast end.
class SpeedScale {
    static TICK_S = 0.05;
    static MIN = 0.0025;        // 1/20 of real time
    static MAX = 2.0;           // 40x real time
    static DEFAULT = 1.0;       // server default (DEFAULT_SPEED in config.py)
    static SLIDER_MAX = 1000;   // slider positions 0..1000

    static fromSlider(pos) {
        return SpeedScale.MIN * Math.pow(SpeedScale.MAX / SpeedScale.MIN, pos / SpeedScale.SLIDER_MAX);
    }

    static toSlider(speed) {
        const ratio = Math.log(speed / SpeedScale.MIN) / Math.log(SpeedScale.MAX / SpeedScale.MIN);
        return Math.round(SpeedScale.SLIDER_MAX * ratio);
    }

    // e.g. "0.05x real time", "1.4x real time", "20x real time"
    static label(speed) {
        const factor = speed / SpeedScale.TICK_S;
        const shown = factor < 1 ? factor.toFixed(2) : factor < 10 ? factor.toFixed(1) : Math.round(factor);
        return shown + "x real time";
    }
}
