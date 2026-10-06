"""The simulation loop. Runs in its own thread and talks to the
aiohttp event loop via asyncio.run_coroutine_threadsafe."""
import asyncio
import threading
import time
from queue import Empty, Queue
from typing import Any, Dict

from aiohttp import web

import config
from agents import handle_req
from matching import process_new_agent
from payloads import build_routes_payload, build_snapshot_payload
from ws_bus import publish, publish_by_id, send_status


def drain_create_queue(q: Queue) -> list:
    reqs = []
    while True:
        try:
            reqs.append(q.get_nowait())
        except Empty:
            return reqs


async def dispatch_frames_by_req_id(app: web.Application, data: Dict[str, Any]) -> None:
    """Send each match frame to the walker's and the driver's request_id."""
    t_s = data["t_s"]
    for frame in data["sims"]:
        event = {"type": "position", "data": {"t_s": t_s, "frame": frame}}
        for rid in (frame["walker"].get("req_id"), frame["driver"].get("req_id")):
            if rid is not None:
                await publish_by_id(app, rid, event)


class Simulation:
    """All state of the running simulation."""

    def __init__(self, app: web.Application, loop: asyncio.AbstractEventLoop):
        self.app = app
        self.loop = loop
        self.t = 0.0
        self.min_saving_m = config.MIN_SAVING_M
        self.matches_sim_list: list = []
        self.driver_agent_list: list = []   # unmatched drivers
        self.walker_agent_list: list = []   # unmatched walkers
        self.agent_id_to_request_id: Dict[str, str] = {}
        self.stop_event = threading.Event()

    # ---- helpers
    def _send(self, coro) -> None:
        asyncio.run_coroutine_threadsafe(coro, self.loop)

    def publish_initial_state(self) -> None:
        for sim in self.matches_sim_list:
            sim.update(0.0)
        routes = build_routes_payload(self.matches_sim_list, version=0.0)
        self.app["routes"] = routes
        self._send(publish(self.app, {"type": "routes", "data": routes}))

        data0 = build_snapshot_payload(
            t_s=0.0,
            sims=self.matches_sim_list,
            driver_agents=self.driver_agent_list,
            walker_agents=self.walker_agent_list,
            include_agent_id=False,
        )
        self.app["last_positions"] = data0
        self._send(publish(self.app, {"type": "positions", "data": data0}))

    # ---- one request from the browser
    def handle_create_request(self, req: dict) -> None:
        req_id, new_agent, kind = handle_req(req, offset=self.t)
        res = process_new_agent(
            kind=kind,
            new_agent=new_agent,
            t=self.t,
            matches_sim_list=self.matches_sim_list,
            driver_agent_list=self.driver_agent_list,
            walker_agent_list=self.walker_agent_list,
            agent_id_to_request_id=self.agent_id_to_request_id,
            handler=None,
            req_id=req_id,
            min_saving_m=self.min_saving_m,
        )

        if res["status"] == "not_matched":
            self._send(send_status(self.app, res["req_id"], "not_matched",
                                   agent_id=res["agent_id"]))
            return

        # matched: tell both sides, then send them the match routes
        self._send(send_status(self.app, res["req_id"], "matched",
                               match_id=res["match_id"], agent_id=res["agent_id"]))
        if res["partner_req_id"] is not None:
            self._send(send_status(self.app, res["partner_req_id"], "matched",
                                   match_id=res["match_id"], agent_id=res["partner_agent_id"]))

        routes_for_this_match = build_routes_payload([res["match_sim"]], version=self.t)
        event = {"type": "routes", "data": routes_for_this_match}
        for rid in (res["req_id"], res["partner_req_id"]):
            if rid is not None:
                self.app["last_routes_by_req"][rid] = routes_for_this_match
                self._send(publish_by_id(self.app, rid, event))

    # ---- one tick
    def step(self) -> None:
        routes_changed = False
        for req in drain_create_queue(self.app["create_q"]):
            self.handle_create_request(req)
            routes_changed = True

        for a in self.driver_agent_list:
            a.update_position(self.t)
        for a in self.walker_agent_list:
            a.update_position(self.t)
        for sim in self.matches_sim_list:
            sim.update(self.t)

        data = build_snapshot_payload(
            t_s=self.t,
            sims=self.matches_sim_list,
            driver_agents=self.driver_agent_list,
            walker_agents=self.walker_agent_list,
            agent_id_to_request_id=self.agent_id_to_request_id,
            include_agent_id=True,
        )
        self.app["last_positions"] = data
        self._send(publish(self.app, {"type": "positions", "data": data}))
        self._send(dispatch_frames_by_req_id(self.app, data))

        if routes_changed:
            routes = build_routes_payload(self.matches_sim_list, version=self.t)
            self._send(publish(self.app, {"type": "routes", "data": routes}))

        self.t += self.app["speed"]

    def run(self) -> None:
        self.publish_initial_state()
        while not self.stop_event.is_set():
            self.step()
            time.sleep(config.TICK_SLEEP_S)


def start_simulation(app: web.Application, loop: asyncio.AbstractEventLoop) -> Simulation:
    sim = Simulation(app, loop)
    threading.Thread(target=sim.run, daemon=True).start()
    return sim
