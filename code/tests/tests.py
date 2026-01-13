# tests.py
import asyncio
import json
import aiohttp

WS_AGENT = "ws://127.0.0.1:8000/ws_agent"
WS_GLOBAL = "ws://127.0.0.1:8000/ws"


async def recvj(ws, t=5):
    m = await asyncio.wait_for(ws.receive(), t)
    if m.type != aiohttp.WSMsgType.TEXT:
        raise RuntimeError(m.type)
    return json.loads(m.data)


async def wait_type(ws, typ, t=5, n=50):
    for _ in range(n):
        o = await recvj(ws, t)
        if o.get("type") == typ:
            return o
    raise RuntimeError(f"no {typ}")


async def _test_global():
    s = aiohttp.ClientSession()
    ws = await s.ws_connect(WS_GLOBAL)

    o1 = await recvj(ws, 5)
    o2 = await recvj(ws, 5)

    await ws.close()
    await s.close()

    types = {o1.get("type"), o2.get("type")}
    if not (("routes" in types) or ("positions" in types)):
        raise RuntimeError(f"unexpected: {types}")


async def _test_ws_by_id():
    s = aiohttp.ClientSession()
    ws = None
    try:
        ws = await s.ws_connect(WS_AGENT)

        walker_payload = {
            "type": "walker",
            "start": {"lat": 51.202561, "lon": 6.780486},
            "dest": {"lat": 51.219105, "lon": 6.787711},
        }
        driver_payload = {
            "type": "driver",
            "start": {"lat": 51.2562, "lon": 7.1508},
            "dest": {"lat": 51.2277, "lon": 6.7735},
        }

        # create walker
        await ws.send_str(json.dumps({"type": "create_request", "payload": walker_payload}))
        w_created = await wait_type(ws, "created", 5)
        w_rid = w_created["request_id"]
        await ws.send_str(json.dumps({"type": "subscribe", "request_id": w_rid}))
        await wait_type(ws, "status", 5)

        # create driver
        await ws.send_str(json.dumps({"type": "create_request", "payload": driver_payload}))
        d_created = await wait_type(ws, "created", 5)
        d_rid = d_created["request_id"]
        await ws.send_str(json.dumps({"type": "subscribe", "request_id": d_rid}))
        await wait_type(ws, "status", 5)

        # expect a match frame that includes BOTH req_ids
        pos = await wait_type(ws, "position", 15)
        data = pos.get("data", {})
        frame = data.get("frame", {}) or {}
        w = frame.get("walker", {}) or {}
        d = frame.get("driver", {}) or {}

        if w.get("req_id") != w_rid:
            raise RuntimeError(f"walker req_id mismatch: got {w.get('req_id')} expected {w_rid}")
        if d.get("req_id") != d_rid:
            raise RuntimeError(f"driver req_id mismatch: got {d.get('req_id')} expected {d_rid}")

    finally:
        if ws is not None:
            await ws.close()
        await s.close()



def test_global():
    asyncio.run(_test_global())


def test_ws_by_id():
    asyncio.run(_test_ws_by_id())

if __name__ == "__main__":
    test_global()
    test_ws_by_id()