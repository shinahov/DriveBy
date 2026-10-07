"""
End-to-end test of the aiohttp server + simulation thread, without OSRM.
Needs aiohttp installed (py -m pip install -r requirements.txt).

Run (from the code folder):
    py -m pytest tests
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fake_osrm import fake_osrm  # noqa: E402

try:
    import aiohttp
    from aiohttp.test_utils import TestClient, TestServer
    HAVE_AIOHTTP = hasattr(aiohttp, "__version__")
except ImportError:
    HAVE_AIOHTTP = False

WALKER = {"type": "walker",
          "start": {"lat": 51.2505, "lon": 7.13},
          "dest": {"lat": 51.2505, "lon": 7.03}}
DRIVER = {"type": "driver",
          "start": {"lat": 51.25, "lon": 7.15},
          "dest": {"lat": 51.25, "lon": 7.00}}


async def wait_for(ws, pred, timeout=5.0):
    """Read messages until pred(msg) is true; return that message."""
    async def loop():
        while True:
            msg = await ws.receive_json()
            if pred(msg):
                return msg
    return await asyncio.wait_for(loop(), timeout)


def is_status(status, request_id=None):
    return lambda m: (m.get("type") == "status" and m.get("status") == status
                      and (request_id is None or m.get("request_id") == request_id))


@unittest.skipUnless(HAVE_AIOHTTP, "aiohttp not installed")
class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._osrm = fake_osrm()
        self._osrm.__enter__()
        from server import create_app
        self.client = TestClient(TestServer(create_app()))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self._osrm.__exit__(None, None, None)

    async def test_health(self):
        r = await self.client.get("/health")
        self.assertEqual(r.status, 200)
        self.assertEqual(await r.text(), "OK")

    async def test_index_serves_map(self):
        r = await self.client.get("/")
        self.assertEqual(r.status, 200)
        self.assertIn("map.js", await r.text())

    async def test_global_ws_gets_positions(self):
        ws = await self.client.ws_connect("/ws")
        msg = await wait_for(ws, lambda m: m.get("type") == "positions")
        self.assertIn("sims", msg["data"])
        await ws.close()

    async def test_walker_then_driver_get_matched(self):
        ws = await self.client.ws_connect("/ws_agent")

        await ws.send_json({"type": "create_request", "payload": WALKER})
        queued = await wait_for(ws, is_status("queued"))
        w_rid = queued["request_id"]
        nm = await wait_for(ws, is_status("not_matched", w_rid))
        self.assertTrue(nm["agent_id"])

        await ws.send_json({"type": "create_request", "payload": DRIVER})
        d_rid = (await wait_for(ws, is_status("queued")))["request_id"]
        self.assertNotEqual(w_rid, d_rid)

        # both requests are told they are matched, with the same match id
        seen = {}
        while len(seen) < 2:
            m = await wait_for(ws, is_status("matched"))
            seen[m["request_id"]] = m["match_id"]
        self.assertEqual(set(seen), {w_rid, d_rid})
        self.assertEqual(seen[w_rid], seen[d_rid])

        # and position frames carry both request ids
        pos = await wait_for(ws, lambda m: m.get("type") == "position")
        frame = pos["data"]["frame"]
        self.assertEqual(frame["walker"]["req_id"], w_rid)
        self.assertEqual(frame["driver"]["req_id"], d_rid)
        await ws.close()

    async def test_subscribe_later_replays_status_and_routes(self):
        ws = await self.client.ws_connect("/ws_agent")
        await ws.send_json({"type": "create_request", "payload": WALKER})
        w_rid = (await wait_for(ws, is_status("queued")))["request_id"]
        await wait_for(ws, is_status("not_matched", w_rid))
        await ws.send_json({"type": "create_request", "payload": DRIVER})
        await wait_for(ws, is_status("matched", w_rid))
        await ws.close()

        # e.g. page reload: a new connection subscribes to the old request_id
        ws2 = await self.client.ws_connect("/ws_agent")
        await ws2.send_json({"type": "subscribe", "request_id": w_rid})
        first = await wait_for(ws2, lambda m: m.get("type") in ("routes", "status"))
        self.assertEqual((first["type"], first["status"]), ("status", "matched"))
        routes = await wait_for(ws2, lambda m: m.get("type") == "routes")
        self.assertEqual(len(routes["data"]["routes"]), 1)
        await wait_for(ws2, is_status("subscribed", w_rid))
        await ws2.close()

    async def test_subscribe_unknown_request(self):
        ws = await self.client.ws_connect("/ws_agent")
        await ws.send_json({"type": "subscribe", "request_id": "does-not-exist"})
        msg = await wait_for(ws, lambda m: m.get("type") == "status")
        self.assertEqual(msg["status"], "unknown")
        await ws.close()

    async def test_unmatched_agent_gets_own_position(self):
        ws = await self.client.ws_connect("/ws_agent")
        await ws.send_json({"type": "create_request", "payload": WALKER})
        await wait_for(ws, is_status("not_matched"))
        msg = await wait_for(ws, lambda m: m.get("type") == "agent_position")
        self.assertEqual(msg["data"]["kind"], "walker")
        self.assertAlmostEqual(msg["data"]["lat"], WALKER["start"]["lat"], places=3)
        await ws.close()

    async def test_unknown_message_type(self):
        ws = await self.client.ws_connect("/ws_agent")
        await ws.send_json({"type": "nonsense"})
        msg = await wait_for(ws, lambda m: "error" in m)
        self.assertEqual(msg["error"], "unknown message type")
        await ws.close()


if __name__ == "__main__":
    unittest.main()
