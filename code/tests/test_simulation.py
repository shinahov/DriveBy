"""
Tests for the simulation loop (simulation.py) and the message queues (ws_bus.py),
without a server: messages to the browser are recorded instead of sent.
"""
import asyncio
import os
import sys
import unittest
from queue import Queue

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fake_osrm import fake_osrm  # noqa: E402

import ws_bus  # noqa: E402
from simulation import Simulation  # noqa: E402

WALKER = {"type": "walker",
          "start": {"lat": 51.2505, "lon": 7.13},
          "dest": {"lat": 51.2505, "lon": 7.03}}
DRIVER = {"type": "driver",
          "start": {"lat": 51.25, "lon": 7.15},
          "dest": {"lat": 51.25, "lon": 7.00}}


class RecordingSimulation(Simulation):
    """Simulation that records what it would send instead of sending it."""

    def __init__(self):
        app = {"create_q": Queue(), "speed": 1.0, "last_routes_by_req": {}}
        super().__init__(app, loop=None)
        self.statuses = []   # (request_id, status, extra)
        self.global_events = []
        self.direct_events = []

    def _send(self, coro):
        coro.close()  # dispatch_frames_by_req_id: not needed here

    def notify_status(self, request_id, status, **extra):
        self.statuses.append((request_id, status, extra))

    def publish_all(self, event, droppable=False):
        self.global_events.append(event)

    def publish_to(self, request_id, event, droppable=False):
        self.direct_events.append((request_id, event))

    def create(self, rid, payload):
        self.app["create_q"].put({"request_id": rid, "payload": payload})

    def status_of(self, rid):
        return [s for r, s, _ in self.statuses if r == rid]


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self._ctx = fake_osrm()
        self._ctx.__enter__()
        self.sim = RecordingSimulation()

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def match_pair(self):
        self.sim.create("w", WALKER)
        self.sim.step()
        self.sim.create("d", DRIVER)
        self.sim.step()
        self.assertEqual(len(self.sim.matches_sim_list), 1)

    def test_walker_then_driver_statuses(self):
        self.match_pair()
        self.assertEqual(self.sim.status_of("w"), ["not_matched", "matched"])
        self.assertEqual(self.sim.status_of("d"), ["matched"])
        self.assertEqual({rid for rid, _ in self.sim.direct_events}, {"w", "d"})
        self.assertIn("w", self.sim.app["last_routes_by_req"])

    def test_bad_request_does_not_stop_simulation(self):
        self.sim.create("bad", {"type": "walker", "start": {"lat": 51.0}})  # no lon, no dest
        self.sim.step()
        self.assertEqual(self.sim.status_of("bad"), ["error"])
        # simulation still works afterwards
        self.match_pair()

    def test_osrm_down_does_not_stop_simulation(self):
        import requests
        from unittest import mock

        def down(*a, **k):
            raise requests.ConnectionError("OSRM not reachable")

        with mock.patch.object(requests, "get", down):
            self.sim.create("x", WALKER)
            self.sim.step()
        self.assertEqual(self.sim.status_of("x"), ["error"])
        self.match_pair()

    def test_finished_match_is_removed_and_driver_is_free_again(self):
        self.match_pair()
        ms = self.sim.matches_sim_list[0]
        end = ms.match.driver_dropoff_eta_s + ms.match.walk_route_from_dropoff.duration
        self.sim.app["speed"] = 10.0
        while self.sim.matches_sim_list and self.sim.t < end + 100:
            self.sim.step()

        self.assertEqual(self.sim.matches_sim_list, [])
        self.assertIn("done", self.sim.status_of("w"))
        # the driver had not reached its destination yet -> waiting again
        self.assertEqual(self.sim.driver_agent_list, [ms.driver_agent])
        self.assertFalse(ms.driver_agent.assigned)
        self.assertEqual(self.sim.status_of("d")[-1], "not_matched")
        # last routes sent to the overview map no longer contain the match
        routes = [e for e in self.sim.global_events if e["type"] == "routes"]
        self.assertEqual(routes[-1]["data"]["routes"], [])

    def test_agents_that_arrived_are_removed(self):
        self.sim.create("w", WALKER)
        self.sim.step()
        self.assertEqual(len(self.sim.walker_agent_list), 1)
        self.sim.app["speed"] = 1000.0
        for _ in range(10):
            self.sim.step()
        self.assertEqual(self.sim.walker_agent_list, [])
        self.assertEqual(self.sim.status_of("w")[-1], "done")
        self.assertNotIn("w", self.sim.agent_id_to_request_id.values())


class LeftoverPositionTests(unittest.TestCase):
    """An agent without a match gets its own position (type "agent_position")."""

    def setUp(self):
        self._ctx = fake_osrm()
        self._ctx.__enter__()
        self.sim = RecordingSimulation()

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def test_unmatched_walker_gets_its_position(self):
        self.sim.create("w", WALKER)
        self.sim.step()
        self.sim.step()
        events = [e for rid, e in self.sim.direct_events if rid == "w" and e["type"] == "agent_position"]
        self.assertTrue(events)
        data = events[-1]["data"]
        self.assertEqual(data["kind"], "walker")
        self.assertEqual(data["agent_id"], self.sim.walker_agent_list[0].agent_id)
        self.assertAlmostEqual(data["lat"], WALKER["start"]["lat"], places=3)

    def test_matched_agents_get_no_agent_position(self):
        self.sim.create("w", WALKER)
        self.sim.step()
        self.sim.create("d", DRIVER)
        self.sim.step()
        self.sim.direct_events.clear()
        self.sim.step()
        self.assertFalse([e for _, e in self.sim.direct_events if e["type"] == "agent_position"])


class WsBusTests(unittest.TestCase):
    def run_async(self, coro):
        return asyncio.run(coro)

    def make_app(self):
        return {"pub_q": asyncio.Queue(), "pub_q_by_id": asyncio.Queue(),
                "subscribers": {"r1": {"ws"}}}

    def test_status_is_never_dropped(self):
        async def go():
            app = self.make_app()
            for i in range(50):
                await ws_bus.publish_by_id(app, "r1", {"type": "position", "i": i},
                                           droppable=True)
            await ws_bus.send_status(app, "r1", "matched", match_id="m")
            items = []
            while not app["pub_q_by_id"].empty():
                items.append(app["pub_q_by_id"].get_nowait())
            return items
        items = self.run_async(go())
        self.assertEqual(len(items), ws_bus.MAX_BACKLOG + 1)
        self.assertEqual(items[-1], ("r1", {"type": "status", "status": "matched",
                                            "request_id": "r1", "match_id": "m"}))

    def test_routes_not_dropped_by_positions(self):
        async def go():
            app = self.make_app()
            await ws_bus.publish(app, {"type": "routes"})
            for _ in range(50):
                await ws_bus.publish(app, {"type": "positions"}, droppable=True)
            return [app["pub_q"].get_nowait() for _ in range(app["pub_q"].qsize())]
        items = self.run_async(go())
        self.assertEqual(items[0], {"type": "routes"})
        self.assertLessEqual(len(items), ws_bus.MAX_BACKLOG)

    def test_newest_status_is_remembered(self):
        async def go():
            app = self.make_app()
            app["last_status_by_req"] = {}
            await ws_bus.send_status(app, "r1", "not_matched", agent_id="a")
            await ws_bus.send_status(app, "r1", "matched", match_id="m")
            await ws_bus.send_status(app, "nobody-listens", "done")
            return app["last_status_by_req"]
        last = self.run_async(go())
        self.assertEqual(last["r1"]["status"], "matched")
        self.assertEqual(last["nobody-listens"]["status"], "done")

    def test_no_subscriber_no_message(self):
        async def go():
            app = self.make_app()
            await ws_bus.send_status(app, "unknown", "matched")
            return app["pub_q_by_id"].qsize()
        self.assertEqual(self.run_async(go()), 0)


if __name__ == "__main__":
    unittest.main()
