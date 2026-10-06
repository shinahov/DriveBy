"""
Characterization tests: they pin down what the backend does TODAY,
so refactoring can't change behaviour unnoticed.

They need no Docker/OSRM: tests/fake_osrm.py answers route requests
with straight lines.

Run (from the code folder):
    py -m pytest tests
or without pytest:
    py -m unittest discover tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fake_osrm import fake_osrm  # noqa: E402

import osrm_client as osrm  # noqa: E402
import geo  # noqa: E402
import agents  # noqa: E402
import matching  # noqa: E402
import payloads  # noqa: E402
from MatchSimulation import Phase  # noqa: E402

# Driver drives straight west along lat 51.25 (~10.4 km).
DRIVER_START = (51.25, 7.15)
DRIVER_DEST = (51.25, 7.00)
# Walker ~55 m north of that road, going the same way (~7 km).
WALKER_START = (51.2505, 7.13)
WALKER_DEST = (51.2505, 7.03)


def payload(kind, start, dest):
    return {"type": kind,
            "start": {"lat": start[0], "lon": start[1]},
            "dest": {"lat": dest[0], "lon": dest[1]}}


class FakeOsrmTestCase(unittest.TestCase):
    def setUp(self):
        self._ctx = fake_osrm()
        self._ctx.__enter__()

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def make_pair(self, w_start=WALKER_START, w_dest=WALKER_DEST):
        d = agents.create_driver_agent(DRIVER_START, DRIVER_DEST, offset=0.0)
        w = agents.create_walker_agent(w_start, w_dest, offset=0.0)
        return d, w


# ---------------------------------------------------------------- geometry

class GeoTests(unittest.TestCase):
    def test_haversine_one_degree_latitude(self):
        self.assertAlmostEqual(geo.haversine_m((50, 7), (51, 7)), 111_195, delta=50)

    def test_haversine_same_point_is_zero(self):
        self.assertEqual(geo.haversine_m((51.2, 7.1), (51.2, 7.1)), 0.0)

    def test_cum_array(self):
        self.assertEqual(geo.cum_array([1.0, 2.0, 3.0]), [0.0, 1.0, 3.0, 6.0])
        self.assertEqual(geo.cum_array([]), [0.0])

    def test_topk_by_haversine_returns_nearest_indices(self):
        pts = [(51.0, 7.0), (51.1, 7.0), (51.2, 7.0), (51.3, 7.0)]
        self.assertEqual(geo.topk_by_haversine(pts, (51.21, 7.0), 2), [2, 3])
        self.assertEqual(len(geo.topk_by_haversine(pts, (51.0, 7.0), 10)), 4)


# ------------------------------------------------------------ routes/agents

class RouteAndAgentTests(FakeOsrmTestCase):
    def test_fetch_route_shape(self):
        r = osrm.fetch_route(DRIVER_START, DRIVER_DEST, "driving")
        self.assertEqual(r["geometry"][0], DRIVER_START)
        self.assertEqual(r["geometry"][-1], DRIVER_DEST)
        self.assertEqual(len(r["geometry"]), len(r["seg_time"]) + 1)
        self.assertEqual(len(r["cum_time"]), len(r["seg_time"]) + 1)
        self.assertAlmostEqual(r["cum_time"][-1], r["total_time"], places=6)
        self.assertAlmostEqual(r["cum_dist"][-1], r["total_dist"], places=6)

    def test_fetch_route_unknown_profile(self):
        with self.assertRaises(ValueError):
            osrm.fetch_route(DRIVER_START, DRIVER_DEST, "cycling")

    def test_walk_fast_returns_distance_and_duration(self):
        m, s = osrm.walk_fast(WALKER_START, WALKER_DEST)
        self.assertGreater(m, 6000)
        self.assertAlmostEqual(s, m / 1.4, delta=1.0)

    def test_create_agents(self):
        d, w = self.make_pair()
        self.assertEqual(d.route.profile, "driving")
        self.assertEqual(w.route.profile, "walking")
        self.assertEqual(d.pos, DRIVER_START)
        self.assertEqual(w.get_pos(), WALKER_START)
        self.assertNotEqual(d.agent_id, w.agent_id)

    def test_agent_moves_along_route(self):
        d, _ = self.make_pair()
        end_t = d.route.cum_time_s[-1]

        d.update_position(-5.0)  # before start
        self.assertEqual(d.get_pos(), DRIVER_START)
        self.assertFalse(d.done)

        d.update_position(end_t / 2)  # halfway
        lat, lon = d.get_pos()
        self.assertAlmostEqual(lon, (DRIVER_START[1] + DRIVER_DEST[1]) / 2, delta=0.002)
        self.assertGreater(d.idx, 0)
        self.assertFalse(d.done)

        d.update_position(end_t + 1)  # past the end
        self.assertEqual(d.get_pos(), DRIVER_DEST)
        self.assertTrue(d.done)

    def test_agent_start_offset_and_time_scale(self):
        d = agents.create_driver_agent(DRIVER_START, DRIVER_DEST, offset=100.0)
        d.update_position(100.0)
        self.assertEqual(d.get_pos(), DRIVER_START)
        d.update_position(150.0)
        pos_normal = d.get_pos()

        d2 = agents.create_driver_agent(DRIVER_START, DRIVER_DEST, offset=100.0)
        d2.time_scale = 2.0
        d2.update_position(125.0)  # 25 s at double speed == 50 s
        self.assertAlmostEqual(d2.get_pos()[1], pos_normal[1], places=9)

    def test_get_pos_at_time_returns_pos_and_index(self):
        d, _ = self.make_pair()
        pos, idx = d.route.get_pos_at_time(d.route.cum_time_s[3] + 0.1)
        self.assertEqual(idx, 3)
        self.assertEqual(len(pos), 2)

    def test_agents_compare_by_id(self):
        d, w = self.make_pair()
        self.assertEqual(d, d)
        self.assertNotEqual(d, w)
        self.assertEqual(len({d, w, d}), 2)

    def test_handle_req(self):
        req = {"request_id": "r1", "payload": payload("walker", WALKER_START, WALKER_DEST)}
        rid, agent, kind = agents.handle_req(req, offset=12.0)
        self.assertEqual((rid, kind), ("r1", "walker"))
        self.assertEqual(agent.route.start, WALKER_START)
        self.assertEqual(agent.start_offset_s, 12.0)

        rid, agent, kind = agents.handle_req(
            {"request_id": "r2", "payload": payload("driver", DRIVER_START, DRIVER_DEST)}, 0.0)
        self.assertEqual(kind, "driver")
        self.assertEqual(agent.route.profile, "driving")


# ---------------------------------------------------------------- matching

class MatchingTests(FakeOsrmTestCase):
    def test_match_found_for_walker_on_the_way(self):
        d, w = self.make_pair()
        m, best = matching.best_match_([d], w, min_saving_m=800.0)
        self.assertIsNotNone(m)
        self.assertIs(best, d)
        self.assertLess(m.pickup_index, m.dropoff_index)
        self.assertGreaterEqual(m.saving_dist_meters, 800.0)
        # walker reaches the pickup before the driver does
        self.assertLessEqual(m.pick_walk_duration_seconds, m.driver_pickup_eta_s)
        self.assertLess(m.driver_pickup_eta_s, m.driver_dropoff_eta_s)
        # pickup/dropoff lie on the driver's route, near walker start/dest
        self.assertIn(m.pickup, d.route.geometry_latlon)
        self.assertIn(m.dropoff, d.route.geometry_latlon)
        self.assertLess(geo.haversine_m(m.pickup, WALKER_START), 100)
        self.assertLess(geo.haversine_m(m.dropoff, WALKER_DEST), 100)
        # walking legs start/end where they should
        self.assertEqual(m.walk_route_to_pickup.start, WALKER_START)
        self.assertEqual(m.walk_route_from_dropoff.dest, WALKER_DEST)
        self.assertAlmostEqual(
            m.total_walk_dist_meters,
            m.pick_walk_dist_meters + m.drop_walk_dist_meters)

    def test_no_match_for_opposite_direction(self):
        d, w = self.make_pair(w_start=WALKER_DEST, w_dest=WALKER_START)
        self.assertEqual(matching.best_match_([d], w), (None, None))

    def test_no_match_when_walker_far_away(self):
        d, w = self.make_pair(w_start=(51.40, 7.13), w_dest=(51.40, 7.03))
        self.assertEqual(matching.best_match_([d], w), (None, None))

    def test_no_match_when_saving_too_small(self):
        d, w = self.make_pair(w_start=(51.2505, 7.13), w_dest=(51.2505, 7.125))
        self.assertEqual(matching.best_match_([d], w), (None, None))

    def test_no_match_without_drivers(self):
        _, w = self.make_pair()
        self.assertEqual(matching.best_match_([], w), (None, None))

    def test_driver_already_past_pickup_does_not_match(self):
        d, w = self.make_pair()
        d.update_position(d.route.cum_time_s[-1] * 0.5)  # driver already at lon 7.075
        self.assertEqual(matching.best_match_([d], w), (None, None))

    def test_best_driver_is_earliest_arrival(self):
        slow = agents.create_driver_agent(DRIVER_START, DRIVER_DEST, offset=0.0)
        fast = agents.create_driver_agent(DRIVER_START, DRIVER_DEST, offset=0.0)
        _, w = self.make_pair()
        # move the "fast" driver closer to the pickup; it arrives earlier
        fast.update_position(60.0)
        m, best = matching.best_match_([slow, fast], w)
        self.assertIs(best, fast)

    def test_create_matches_removes_matched_agents(self):
        d, w = self.make_pair()
        drivers, walkers = [d], [w]
        sims, d_left, w_left = matching.create_matches(drivers, walkers, now_t=5.0)
        self.assertEqual(len(sims), 1)
        self.assertEqual((d_left, w_left), ([], []))
        self.assertIs(drivers, d_left)  # lists are mutated in place
        self.assertTrue(d.assigned and w.assigned)
        sim = sims[0]
        self.assertIs(sim.driver_agent, d)
        self.assertIs(sim.walker_agent, w)
        self.assertEqual(sim.creation_time_s, 5.0)
        self.assertEqual(sim.walk_to_pickup_agent.start_offset_s, 5.0)
        self.assertAlmostEqual(sim.walk_from_dropoff_agent.start_offset_s,
                               5.0 + sim.match.driver_dropoff_eta_s)

    def test_create_matches_keeps_unmatched(self):
        d, w = self.make_pair(w_start=WALKER_DEST, w_dest=WALKER_START)
        sims, d_left, w_left = matching.create_matches([d], [w], now_t=0.0)
        self.assertEqual(sims, [])
        self.assertEqual((d_left, w_left), ([d], [w]))
        self.assertFalse(d.assigned or w.assigned)

    def test_process_new_agent_walker_then_driver(self):
        sims, drivers, walkers, ids = [], [], [], {}
        w = agents.create_walker_agent(WALKER_START, WALKER_DEST, offset=0.0)
        res = matching.process_new_agent("walker", w, 0.0, sims, drivers, walkers,
                                         ids, None, "req-w", 800.0)
        self.assertEqual(res, {"status": "not_matched", "req_id": "req-w",
                               "agent_id": w.agent_id})
        self.assertEqual(walkers, [w])
        self.assertEqual(ids[w.agent_id], "req-w")

        d = agents.create_driver_agent(DRIVER_START, DRIVER_DEST, offset=0.0)
        res = matching.process_new_agent("driver", d, 0.0, sims, drivers, walkers,
                                         ids, None, "req-d", 800.0)
        self.assertEqual(res["status"], "matched")
        self.assertEqual(res["req_id"], "req-d")
        self.assertEqual(res["agent_id"], d.agent_id)
        self.assertEqual(res["partner_req_id"], "req-w")
        self.assertEqual(res["partner_agent_id"], w.agent_id)
        self.assertIs(res["match_sim"], sims[0])
        self.assertEqual(res["match_id"], sims[0].match_id)
        self.assertEqual((drivers, walkers), ([], []))

    def test_process_new_agent_driver_then_walker(self):
        sims, drivers, walkers, ids = [], [], [], {}
        d = agents.create_driver_agent(DRIVER_START, DRIVER_DEST, offset=0.0)
        res = matching.process_new_agent("driver", d, 0.0, sims, drivers, walkers,
                                         ids, None, "req-d", 800.0)
        self.assertEqual(res["status"], "not_matched")
        self.assertEqual(drivers, [d])

        w = agents.create_walker_agent(WALKER_START, WALKER_DEST, offset=0.0)
        res = matching.process_new_agent("walker", w, 0.0, sims, drivers, walkers,
                                         ids, None, "req-w", 800.0)
        self.assertEqual(res["status"], "matched")
        self.assertEqual(res["partner_req_id"], "req-d")
        self.assertEqual((drivers, walkers), ([], []))
        self.assertEqual(len(sims), 1)

    def test_process_new_agent_unknown_kind(self):
        d, _ = self.make_pair()
        with self.assertRaises(ValueError):
            matching.process_new_agent("bike", d, 0.0, [], [], [], {}, None, "r", 800.0)


# ---------------------------------------------------- match simulation

class MatchSimulationTests(FakeOsrmTestCase):
    def make_sim(self):
        d, w = self.make_pair()
        sims, _, _ = matching.create_matches([d], [w], now_t=0.0)
        return sims[0]

    def test_phases_run_in_order_and_finish(self):
        sim = self.make_sim()
        order = [Phase.WALK_TO_PICKUP, Phase.WAIT_AT_PICKUP, Phase.RIDE_WITH_DRIVER,
                 Phase.WALK_FROM_DROPOFF, Phase.DONE]
        seen = []
        end = sim.match.driver_dropoff_eta_s + sim.match.walk_route_from_dropoff.duration + 5
        t = 0.0
        while t <= end:
            sim.update(t)
            if not seen or seen[-1] != sim.phase:
                seen.append(sim.phase)
            if sim.phase == Phase.RIDE_WITH_DRIVER:
                self.assertEqual(sim.get_walker_pos(), sim.get_driver_pos())
            if sim.phase == Phase.WAIT_AT_PICKUP:
                self.assertEqual(sim.get_walker_pos(), sim.match.pickup)
            t += 1.0
        self.assertEqual(seen, order)
        self.assertEqual(sim.get_walker_pos(), WALKER_DEST)

    def test_walker_starts_at_own_position(self):
        sim = self.make_sim()
        sim.update(0.0)
        self.assertEqual(sim.phase, Phase.WALK_TO_PICKUP)
        self.assertEqual(sim.get_walker_pos(), WALKER_START)
        self.assertEqual(sim.get_driver_pos(), DRIVER_START)


# ---------------------------------------------- payloads sent to the browser

class PayloadTests(FakeOsrmTestCase):
    def setUp(self):
        super().setUp()
        d, w = self.make_pair()
        self.sims, _, _ = matching.create_matches([d], [w], now_t=0.0)
        self.sims[0].update(0.0)
        self.left_d = agents.create_driver_agent((51.3, 7.1), (51.3, 7.0), offset=0.0)
        self.left_w = agents.create_walker_agent((51.3, 7.1), (51.3, 7.09), offset=0.0)

    def test_routes_payload(self):
        p = payloads.build_routes_payload(self.sims, version=3.5)
        self.assertEqual(p["routes_version"], 3.5)
        self.assertEqual(len(p["routes"]), 1)
        r = p["routes"][0]
        self.assertEqual(set(r), {"match_id", "driver_route", "walk_to_pickup",
                                  "walk_from_dropoff", "points", "idx"})
        self.assertEqual(r["match_id"], self.sims[0].match_id)
        self.assertEqual(set(r["points"]), {"pickup", "dropoff"})
        self.assertEqual(set(r["idx"]), {"pickup", "dropoff"})
        self.assertTrue(r["driver_route"]["geometry_latlon"])

    def test_routes_payload_skips_finished_matches(self):
        self.sims[0].update(1e9)
        self.assertEqual(self.sims[0].phase, Phase.DONE)
        self.assertEqual(payloads.build_routes_payload(self.sims, 0.0)["routes"], [])

    def test_snapshot_payload(self):
        sim = self.sims[0]
        ids = {sim.walker_agent.agent_id: "req-w", sim.driver_agent.agent_id: "req-d"}
        p = payloads.build_snapshot_payload(7.0, self.sims, [self.left_d], [self.left_w],
                                            agent_id_to_request_id=ids)
        self.assertEqual(set(p), {"t_s", "sims", "leftover_drivers", "leftover_walkers"})
        self.assertEqual(p["t_s"], 7.0)
        f = p["sims"][0]
        self.assertEqual(set(f), {"sim_id", "phase", "walker", "driver", "meta"})
        self.assertEqual(f["sim_id"], sim.match_id)
        self.assertEqual(f["phase"], "WALK_TO_PICKUP")
        self.assertEqual(set(f["walker"]), {"agent_id", "req_id", "lat", "lon", "pIdx", "dIdx"})
        self.assertEqual(set(f["driver"]), {"agent_id", "req_id", "lat", "lon", "idx"})
        self.assertEqual(f["walker"]["req_id"], "req-w")
        self.assertEqual(f["driver"]["req_id"], "req-d")
        self.assertEqual(set(f["meta"]), {"t_driver_pickup", "t_driver_dropoff"})
        self.assertEqual(p["leftover_drivers"],
                         [{"lat": 51.3, "lon": 7.1, "agent_id": self.left_d.agent_id}])
        self.assertEqual(p["leftover_walkers"][0]["agent_id"], self.left_w.agent_id)

    def test_snapshot_payload_without_ids(self):
        p = payloads.build_snapshot_payload(0.0, self.sims, [self.left_d], [],
                                            include_agent_id=False)
        self.assertIsNone(p["sims"][0]["walker"]["req_id"])
        self.assertEqual(p["leftover_drivers"], [{"lat": 51.3, "lon": 7.1}])


if __name__ == "__main__":
    unittest.main()
