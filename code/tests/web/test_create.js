// Tests for web/create.js (+ create_flow.js, navigation.js, match_layers.js) without a browser.
// Run from the code folder:  node tests/web/test_create.js
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const { makeContext } = require('./fake_leaflet');
const WEB = process.argv[2] || require('path').join(__dirname, '..', '..', 'web');
const FILES = ['status.js', 'geo.js', 'match_layers.js', 'navigation.js', 'create_flow.js', 'create.js'];
const eq = (a, b, m) => assert.strictEqual(JSON.stringify(a), JSON.stringify(b), m);

function load(storage) {
  const t = makeContext();
  if (storage) Object.assign(t.storage, storage);
  vm.createContext(t.ctx);
  for (const f of FILES) vm.runInContext(fs.readFileSync(WEB + '/' + f, 'utf8'), t.ctx, { filename: f });
  vm.runInContext('this.__get = (n) => eval(n);', t.ctx);
  return t;
}
const click = (t, lat, lng) => t.map.fire('click', { latlng: { lat, lng } });
function createWalker(t) {
  t.els['btn-kind-walker'].onclick(); click(t, 51.2, 6.78); t.els['btn-confirm'].onclick();
  click(t, 51.21, 6.79); t.els['btn-confirm'].onclick();
}
function route(id) { const d = [[51,7],[51,7.01],[51,7.02],[51,7.03],[51,7.04]];
  return { match_id: id, driver_route: { geometry_latlon: d }, walk_to_pickup: { geometry_latlon: [[51.001,7.0],[51.0005,7.005],d[1]] },
    walk_from_dropoff: { geometry_latlon: [d[3],[51.0005,7.035],[51.001,7.04]] }, points: { pickup: d[1], dropoff: d[3] }, idx: { pickup: 1, dropoff: 3 } }; }
const frame = (phase, o = {}) => ({ type: 'position', data: { t_s: 1, frame: Object.assign({ sim_id: 'M1', phase,
  walker: { agent_id: 'W', lat: 51.0005, lon: 7.005, pIdx: 1, dIdx: 0 }, driver: { agent_id: 'D', lat: 51, lon: 7.0, idx: 0 } }, o) } });
const st = (status, extra = {}) => Object.assign({ type: 'status', status, request_id: 'R1' }, extra);

// ---- create flow
let t = load(); let s = t.sock.s;
createWalker(t);
assert.strictEqual(t.els['btn-create'].disabled, false);
t.sock.open = false; t.els['btn-create'].onclick();
assert.match(t.els['msg'].textContent, /Not connected/);
assert.strictEqual(t.els['btn-create'].disabled, false, 'buttons unlocked again');
t.sock.open = true; t.els['btn-create'].onclick();
eq(t.sent[0].payload, { type: 'walker', start: { lat: 51.2, lon: 6.78 }, dest: { lat: 51.21, lon: 6.79 } });
assert.strictEqual(t.els['btn-create'].disabled, true);

// ---- statuses
s.h.status(st('queued'));
s.onConnect(); eq(t.sent.at(-1), { type: 'subscribe', request_id: 'R1' });
s.h.status(st('error', { message: 'boom' })); assert.match(t.els['msg'].textContent, /boom/);
const nSent = t.sent.length; t.els['btn-create'].onclick();
assert.strictEqual(t.sent.length, nSent + 1, 'can create again after an error');
s.h.status(st('queued'));
s.h.status(st('not_matched', { agent_id: 'W' }));
// waiting: my own dot follows agent_position
s.h.agent_position({ type: 'agent_position', data: { t_s: 1, kind: 'walker', agent_id: 'OTHER', lat: 1, lon: 1 } });
assert.strictEqual(t.ctx.__get('myLeftoverMarker'), null, 'other agent ignored');
s.h.agent_position({ type: 'agent_position', data: { t_s: 1, kind: 'walker', agent_id: 'W', lat: 51.2, lon: 6.78 } });
const dot = t.ctx.__get('myLeftoverMarker');
assert.ok(dot && t.onMap.has(dot), 'waiting dot shown');
s.h.status(st('matched', { match_id: 'M1', agent_id: 'W' }));
assert.ok(!t.onMap.has(dot), 'waiting dot removed after match');
assert.strictEqual(t.els['btn-follow'].hidden, false);

// ---- match route + progress
s.h.routes({ type: 'routes', data: { routes: [route('OTHER'), route('M1')] } });
let m = t.ctx.__get('myMatch');
assert.ok(m, 'match drawn');
assert.strictEqual(t.map.calls.filter(c => c[0] === 'fitBounds').length, 1);
s.h.position(frame('WALK_TO_PICKUP', { walker: { lat: 51.0005, lon: 7.005, pIdx: 1, dIdx: 0 }, driver: { lat: 51, lon: 7.0, idx: 0 } }));
assert.strictEqual(m.lines.walkTo.ll.length, 2, 'walked part of walk-to-pickup hidden');
s.h.position(frame('RIDE_WITH_DRIVER', { walker: { lat: 51, lon: 7.02, pIdx: 2, dIdx: 0 }, driver: { lat: 51, lon: 7.02, idx: 2 } }));
assert.strictEqual(m.lines.pre.ll.length, 0, 'driver passed pickup');
assert.strictEqual(m.lines.ride.ll.length, 2, 'ride from idx 2 to 3');
assert.strictEqual(m.lines.walkTo.ll.length, 0, 'walk to pickup is done while riding');
assert.strictEqual(m.lines.walkFrom.ll.length, 3, 'walk from dropoff not started');
s.h.position(frame('WALK_FROM_DROPOFF', { walker: { lat: 51.0005, lon: 7.035, pIdx: 2, dIdx: 1 }, driver: { lat: 51, lon: 7.04, idx: 4 } }));
assert.strictEqual(m.lines.walkFrom.ll.length, 2, 'walked part of walk from dropoff hidden');
// position of another match is ignored
s.h.position({ type: 'position', data: { t_s: 2, frame: { sim_id: 'X', phase: 'WALK_TO_PICKUP', walker: { lat: 0, lon: 0, pIdx: 0, dIdx: 0 }, driver: { lat: 0, lon: 0, idx: 0 } } } });
const wm = t.ctx.__get('myWalkerMarker');
assert.notStrictEqual(wm.ll[0], 0);
// ---- follow mode
t.els['btn-follow'].onclick();
assert.strictEqual(t.els['btn-stop-follow'].hidden, false);
const before = t.map.calls.length;
s.h.position(frame('WALK_TO_PICKUP', { walker: { lat: 51.0005, lon: 7.005, pIdx: 1, dIdx: 0 }, driver: { lat: 51, lon: 7.03, idx: 3 } }));
const fly = t.map.calls.slice(before).find(c => c[0] === 'flyTo');
assert.ok(fly, 'first follow update flies to a zoom');
assert.ok([16,17,18,19].includes(fly[1]));
assert.notStrictEqual(t.map.bearing, 0, 'map rotated to walking direction');
// the walker's map follows the right route in each phase
const f = t.ctx.__get('follower'); const used = []; const orig = f.update.bind(f);
f.update = (pos, r, idx, a, b) => { used.push([r, idx]); orig(pos, r, idx, a, b); };
const mm = t.ctx.__get('myMatch');
s.h.position(frame('WALK_TO_PICKUP', { walker: { lat: 51.0005, lon: 7.005, pIdx: 1, dIdx: 0 }, driver: { lat: 51, lon: 7.0, idx: 0 } }));
s.h.position(frame('RIDE_WITH_DRIVER', { walker: { lat: 51, lon: 7.015, pIdx: 2, dIdx: 0 }, driver: { lat: 51, lon: 7.015, idx: 1 } }));
s.h.position(frame('WALK_FROM_DROPOFF', { walker: { lat: 51.0005, lon: 7.035, pIdx: 2, dIdx: 1 }, driver: { lat: 51, lon: 7.04, idx: 4 } }));
assert.ok(used[0][0] === mm.walkTo && used[0][1] === 1, 'walk to pickup');
assert.ok(used[1][0] === mm.driver && used[1][1] === 1, 'ride on driver route');
assert.ok(used[2][0] === mm.walkFrom && used[2][1] === 1, 'walk from dropoff');
// user drags the map -> following stops, "Navigate" is offered again
t.map.fire('dragstart');
assert.strictEqual(t.ctx.__get('follower').enabled, false);
assert.strictEqual(t.els['btn-follow'].hidden, false);
t.els['btn-follow'].onclick();
assert.strictEqual(t.ctx.__get('follower').enabled, true);
t.els['btn-stop-follow'].onclick();
const n = t.map.calls.length;
s.h.position(frame('WALK_TO_PICKUP'));
assert.ok(!t.map.calls.slice(n).some(c => c[0] === 'flyTo' || c[0] === 'panTo'), 'no follow after stop');
const matchLayers = t.ctx.__get('myMatch').all;
s.h.status(st('done'));
assert.match(t.els['msg'].textContent, /Arrived|finished/i);
assert.ok(matchLayers.every(l => !t.onMap.has(l)), 'match removed when done');
assert.strictEqual(t.els['btn-follow'].hidden, true);
// driver whose walker got off: back to waiting
t = load(); s = t.sock.s;
s.h.status(st('queued')); s.h.status(st('matched', { match_id: 'M1', agent_id: 'D' }));
s.h.routes({ type: 'routes', data: { routes: [route('M1')] } });
const ml = t.ctx.__get('myMatch').all;
s.h.status(st('not_matched', { agent_id: 'D' }));
assert.ok(ml.every(l => !t.onMap.has(l)), 'old match removed');
assert.strictEqual(t.ctx.__get('viewMode'), 'agent');
console.log('create.js base OK');

// ---- reload keeps my agent
{
  let t1 = load(); const s1 = t1.sock.s;
  createWalker(t1); t1.els['btn-create'].onclick();
  s1.h.status(st('queued'));
  const stored = JSON.parse(t1.storage['driveby.myAgent']);
  eq(stored, { requestId: 'R1', kind: 'walker' });

  // "reload": new page with the same sessionStorage
  const t2 = load(t1.storage); const s2 = t2.sock.s;
  assert.strictEqual(t2.ctx.__get('myRequestId'), 'R1');
  assert.strictEqual(t2.ctx.__get('createdKind'), 'walker');
  assert.strictEqual(t2.els['btn-create'].disabled, true, 'create panel locked');
  s2.onConnect(); eq(t2.sent.at(-1), { type: 'subscribe', request_id: 'R1' });
  s2.h.status(st('matched', { match_id: 'M1', agent_id: 'W' }));
  s2.h.routes({ type: 'routes', data: { routes: [route('M1')] } });
  assert.ok(t2.ctx.__get('myMatch'), 'match back after reload');
  s2.h.status(st('done'));
  assert.strictEqual(t2.storage['driveby.myAgent'], undefined, 'forgotten when done');

  // server restarted: unknown id -> back to create mode
  const t3 = load({ 'driveby.myAgent': JSON.stringify({ requestId: 'OLD', kind: 'driver' }) });
  t3.sock.s.h.status({ type: 'status', status: 'unknown', request_id: 'OLD' });
  assert.strictEqual(t3.ctx.__get('viewMode'), 'create');
  assert.strictEqual(t3.storage['driveby.myAgent'], undefined);
  assert.strictEqual(t3.els['btn-kind-walker'].disabled, false);
  console.log('create.js reload OK');
}
