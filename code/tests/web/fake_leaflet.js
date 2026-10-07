// Fake Leaflet + DOM for running the page scripts in node (test only).
const onMap = new Set();
class Layer {
  constructor(kind, ll, opts){ this.kind=kind; this.ll=ll; this.opts=opts||{}; this.h={}; }
  addTo(m){ onMap.add(this); return this; } bindTooltip(t){ this.tip=t; return this; }
  setLatLng(ll){ this.ll=ll; return this; } setLatLngs(p){ this.ll=p; return this; }
  getLatLng(){ return this.ll; } on(e,f){ this.h[e]=f; return this; }
}
function makeMap() {
  const handlers = {};
  return { handlers, zoom: 12, bearing: 0, calls: [],
    setView(c,z){ this.zoom = z ?? this.zoom; }, invalidateSize(){}, whenReady(f){ f(); },
    fitBounds(p){ this.calls.push(['fitBounds', p.length]); },
    on(e,f){ (handlers[e] = handlers[e] || []).push(f); return this; },
    once(e,f){ this.on(e,f); }, off(){},
    fire(e, ev){ (handlers[e]||[]).forEach(f=>f(ev||{})); },
    removeLayer(l){ onMap.delete(l); }, hasLayer(l){ return onMap.has(l); },
    setBearing(b){ this.bearing = b; }, getZoom(){ return this.zoom; },
    project(ll){ return {x: ll[1]*1000, y: -ll[0]*1000}; }, unproject(p){ return [-p.y/1000, p.x/1000]; },
    flyTo(c,z){ this.calls.push(['flyTo', z]); this.zoom = z; }, panTo(c){ this.calls.push(['panTo']); },
    getCenter(){ return [0,0]; }, getContainer(){ return containerEl; } };
}
const containerEl = { listeners: {}, addEventListener(e,f){ (this.listeners[e]=this.listeners[e]||[]).push(f); } };
function makeContext(extra) {
  const map = makeMap();
  const L = { map: () => map, tileLayer: () => new Layer('tile'), marker: (ll,o) => new Layer('marker', ll, o),
    divIcon: () => ({}), icon: () => ({}), circleMarker: (ll,o) => new Layer('circle', ll, o),
    polyline: (p,o) => new Layer('line', p, o), point: (x,y) => ({x,y}) };
  const els = {};
  const el = () => ({ textContent:'', hidden:true, disabled:false, style:{display:'none'}, value:'1' });
  const sent = [];
  const sock = { open: true };
  class LiveSocket { constructor(p){ this.path=p; this.h={}; sock.s=this; } on(t,f){ this.h[t]=f; return this; }
    send(o){ if (!sock.open) return false; sent.push(JSON.parse(JSON.stringify(o))); return true; } }
  const storage = {};
  const ctx = Object.assign({ L, LiveSocket, console: { log(){}, warn(){}, error: console.error },
    requestAnimationFrame: f => f(), setTimeout(){}, setInterval(){}, window: { open(){}, close(){} },
    document: { getElementById: id => (els[id] = els[id] || el()) },
    sessionStorage: { getItem: k => storage[k] ?? null, setItem: (k,v) => { storage[k] = String(v); }, removeItem: k => { delete storage[k]; } },
    performance: { now: () => Date.now() }, Date, Math, Number, String, Array, Object, JSON, Set, Map },
    extra || {});
  return { ctx, map, onMap, els, sent, sock, storage, Layer };
}
module.exports = { makeContext };
