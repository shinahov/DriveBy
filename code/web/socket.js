// One WebSocket connection that reconnects by itself.
// Usage:
//   const socket = new LiveSocket("/ws")
//       .on("routes", msg => ...)
//       .on("positions", msg => ...);
//   socket.onConnect = () => ...;   // optional: runs after every (re)connect
//   socket.send({type: "..."});
class LiveSocket {
    constructor(path) {
        const scheme = location.protocol === "https:" ? "wss://" : "ws://";
        this.url = scheme + location.host + path;
        this.handlers = {};     // message type -> function
        this.onConnect = null;
        this.connect();
    }

    on(type, fn) {
        this.handlers[type] = fn;
        return this;
    }

    isOpen() {
        return this.ws.readyState === WebSocket.OPEN;
    }

    send(obj) {
        if (!this.isOpen()) {
            console.warn("socket not open, not sent:", obj);
            return false;
        }
        this.ws.send(JSON.stringify(obj));
        return true;
    }

    connect() {
        this.ws = new WebSocket(this.url);
        this.ws.onopen = () => {
            console.log("connected", this.url);
            if (this.onConnect) this.onConnect();
        };
        this.ws.onclose = () => {
            console.log("disconnected, retry in 2s", this.url);
            setTimeout(() => this.connect(), 2000);
        };
        this.ws.onerror = () => this.ws.close();
        this.ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            const fn = this.handlers[msg.type];
            if (fn) fn(msg);
        };
    }
}
