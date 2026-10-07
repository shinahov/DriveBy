// Tests for web/map.js without a browser: Leaflet and the page are faked (fake_leaflet.js).
// Run from the code folder:  node tests/web/test_map.js
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const { makeContext } = require('./fake_leaflet');
const WEB = process.argv[2] || require('path').join(__dirname, '..', '..', 'web');
const t = makeContext();
vm.createContext(t.ctx);
for (const f of ['geo.js', 'match_layers.js', 'map.js']) {
  vm.runInContext(fs.readFileSync(WEB + '/' + f, 'utf8'), t.ctx, { filename: f });
}
vm.runInContext('this.__sims = () => sims; this.__focus = k => setFocus(k);', t.ctx);
const s = t.sock.s;
function route(id, sh) { const d = [[51,7+sh],[51,7.01+sh],[51,7.02+sh],[51,7.03+sh]];
  return { match_id: id, driver_route: { geometry_latlon: d }, walk_to_pickup: { geometry_latlon: [[51.001,7+sh], d[1]] },
    walk_from_dropoff: { geometry_latlon: [d[2], [51.001,7.03+sh]] }, points: { pickup: d[1], dropoff: d[2] }, idx: { pickup: 1, dropoff: 2 } }; }
const frame = (id, lon) => ({ sim_id: id, phase: 'X', walker: { lat: 51, lon }, driver: { lat: 51, lon: lon + 0.001 } });
const pos = (t_s, frames, lD = [], lW = []) => ({ data: { t_s, sims: frames, leftover_drivers: lD, leftover_walkers: lW } });

s.h.routes({ data: { routes_version: 1, routes: [route('A',0), route('B',1), route('C',2)] } });
s.h.positions(pos(1, [frame('A',7), frame('B',8), frame('C',9)]));
let sims = t.ctx.__sims();
assert.deepStrictEqual(Object.keys(sims).sort(), ['A','B','C']);
const bRide = sims.B.match.lines.ride;
assert.strictEqual(bRide.ll[0][1], 8.01);
let aLayers = sims.A.match.all;
const fits = () => t.map.calls.filter(c => c[0] === 'fitBounds').length;
assert.strictEqual(fits(), 1);
s.h.routes({ data: { routes_version: 1.5, routes: [route('A',0), route('B',1), route('C',2)] } });
assert.strictEqual(fits(), 1, 'same matches again: map does not jump');
s.h.routes({ data: { routes_version: 1.7, routes: [route('A',0), route('B',1), route('C',2), route('D',3)] } });
assert.strictEqual(fits(), 2, 'new match: zoom to it');
s.h.positions(pos(1.8, [frame('A',7), frame('B',8), frame('C',9)]));
aLayers = t.ctx.__sims().A.match.all;
// A finished
s.h.positions(pos(2, [frame('B',8), frame('C',9)]));
sims = t.ctx.__sims();
assert.deepStrictEqual(Object.keys(sims).sort(), ['B','C']);
assert.ok(t.onMap.has(sims.B.match.lines.ride));
assert.ok(aLayers.every(l => !t.onMap.has(l)), 'A layers removed');
assert.strictEqual(sims.C.walker.ll[1], 9);
// focus on C hides B
t.ctx.__focus('M:C');
assert.ok(!t.onMap.has(sims.B.walker) && !t.onMap.has(sims.B.match.lines.ride));
assert.ok(t.onMap.has(sims.C.walker) && t.onMap.has(sims.C.match.lines.ride));
t.map.fire('dblclick');
assert.ok(t.onMap.has(sims.B.walker));
// leftovers + focus on one agent
s.h.positions(pos(3, [frame('B',8)], [{ lat: 51.1, lon: 7.1, agent_id: 'd1' }], [{ lat: 51.2, lon: 7.2, agent_id: 'w1' }, { lat: 51.3, lon: 7.3, agent_id: 'w2' }]));
assert.match(t.els['info'].textContent, /left walkers = 2/);
t.ctx.__focus('A:w2');
const visibleCircles = [...t.onMap].filter(l => l.kind === 'circle' && l.opts.radius === 5);
assert.strictEqual(visibleCircles.length, 1);
assert.strictEqual(JSON.stringify(visibleCircles[0].ll), '[51.3,7.3]');
// speed box closes on a click on the map
t.els['btn-speed'].onclick();
assert.strictEqual(t.els['speedBox'].style.display, 'block');
t.map.fire('click', { latlng: { lat: 51, lng: 7 } });
assert.strictEqual(t.els['speedBox'].style.display, 'none');
// speed control sends the value
t.els['speedRange'].value = '0.5'; t.els['speedRange'].onchange();
assert.strictEqual(JSON.stringify(t.sent.at(-1)), '{"type":"speed","value":0.5}');
console.log('map.js OK');
