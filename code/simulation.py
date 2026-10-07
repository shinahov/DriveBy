"""The simulation loop. Runs in its own thread and talks to the
aiohttp event loop via asyncio.run_coroutine_threadsafe."""
import asyncio
import threading
import time
import traceback
from queue import Empty, Queue
from typing import Any, Dict

from aiohttp import web

import config
from agents import create_walker_agent, handle_req
from matching import process_new_agent
from MatchSimulation import Phase
from payloads import build_routes_payload, build_snapshot_payload
from status import Status
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
                await publish_by_id(app, rid, event, droppable=True)


def leftover_events(data: Dict[str, Any], agent_id_to_request_id: Dict[str, str]) -> list:
    """(request_id, event) for every unmatched agent, so its page can show where it is."""
    events = []
    for kind, key in (("driver", "leftover_drivers"), ("walker", "leftover_walkers")):
        for a in data[key]:
            rid = agent_id_to_request_id.get(a.get("agent_id"))
            if rid is None:
                continue
            events.append((rid, {"type": "agent_position",
                                 "data": {"t_s": data["t_s"], "kind": kind, **a}}))
    return events


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

    # ---- sending to the browsers (runs the coroutine on the aiohttp loop)
    def _send(self, coro) -> None:
        asyncio.run_coroutine_threadsafe(coro, self.loop)

    def notify_status(self, request_id: str, status: str, **extra) -> None:
        self._send(send_status(self.app, request_id, status, **extra))

    def publish_all(self, event: dict, droppable: bool = False) -> None:
        self._send(publish(self.app, event, droppable=droppable))

    def publish_to(self, request_id: str, event: dict, droppable: bool = False) -> None:
        self._send(publish_by_id(self.app, request_id, event, droppable=droppable))

    def publish_initial_state(self) -> None:
        for sim in self.matches_sim_list:
            sim.update(0.0)
        routes = build_routes_payload(self.matches_sim_list, version=0.0)
        self.app["routes"] = routes
        self.publish_all({"type": "routes", "data": routes})

        data0 = build_snapshot_payload(
            t_s=0.0,
            sims=self.matches_sim_list,
            driver_agents=self.driver_agent_list,
            walker_agents=self.walker_agent_list,
            include_agent_id=False,
        )
        self.app["last_positions"] = data0
        self.publish_all({"type": "positions", "data": data0}, droppable=True)

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

        if res["status"] == Status.NOT_MATCHED:
            self.notify_status(res["req_id"], Status.NOT_MATCHED, agent_id=res["agent_id"])
            return

        # matched: tell both sides, then send them the match routes
        self.notify_status(res["req_id"], Status.MATCHED,
                           match_id=res["match_id"], agent_id=res["agent_id"])
        if res["partner_req_id"] is not None:
            self.notify_status(res["partner_req_id"], Status.MATCHED,
                               match_id=res["match_id"], agent_id=res["partner_agent_id"])

        routes_for_this_match = build_routes_payload([res["match_sim"]], version=self.t)
        event = {"type": "routes", "data": routes_for_this_match}
        for rid in (res["req_id"], res["partner_req_id"]):
            if rid is not None:
                self.app["last_routes_by_req"][rid] = routes_for_this_match
                self.publish_to(rid, event)

    # ---- the user cancels his trip
    def request_id_to_agent_id(self, request_id: str):
        for agent_id, rid in self.agent_id_to_request_id.items():
            if rid == request_id:
                return agent_id
        return None

    def cancel(self, request_id: str) -> None:
        """Remove the agent of request_id. If it was matched, the partner waits for a
        new match: a driver just drives on, a walker walks on from where he is now."""
        agent_id = self.request_id_to_agent_id(request_id)
        self.agent_id_to_request_id.pop(agent_id, None)

        for lst in (self.driver_agent_list, self.walker_agent_list):
            lst[:] = [a for a in lst if a.agent_id != agent_id]

        for sim in [s for s in self.matches_sim_list
                    if agent_id in (s.walker_agent.agent_id, s.driver_agent.agent_id)]:
            self.matches_sim_list.remove(sim)
            if sim.driver_agent.agent_id == agent_id:
                self.free_walker(sim)
            else:
                self.free_driver(sim)

        self.notify_status(request_id, Status.CANCELLED)

    def free_driver(self, sim) -> None:
        driver = sim.driver_agent
        rid = self.agent_id_to_request_id.get(driver.agent_id)
        if driver.done:
            self.agent_id_to_request_id.pop(driver.agent_id, None)
            if rid is not None:
                self.notify_status(rid, Status.DONE, match_id=sim.match_id)
            return
        driver.assigned = False
        self.driver_agent_list.append(driver)
        if rid is not None:
            self.notify_status(rid, Status.NOT_MATCHED, agent_id=driver.agent_id)

    def free_walker(self, sim) -> None:
        old = sim.walker_agent
        rid = self.agent_id_to_request_id.get(old.agent_id)
        # new walking route from where the walker is now (same id, so his page keeps working)
        try:
            walker = create_walker_agent(sim.get_walker_pos(), old.route.dest, offset=self.t)
        except Exception as e:  # e.g. OSRM down: the walker is dropped, his page is told
            traceback.print_exc()
            self.agent_id_to_request_id.pop(old.agent_id, None)
            if rid is not None:
                self.notify_status(rid, Status.ERROR, message=f"Driver cancelled, no new route: {e}")
            return
        walker.agent_id = old.agent_id
        self.walker_agent_list.append(walker)
        if rid is not None:
            self.notify_status(rid, Status.NOT_MATCHED, agent_id=walker.agent_id)

    # ---- finished matches / agents
    def remove_finished(self) -> bool:
        """Drop finished matches; their driver becomes free again if still driving.
        Also drop unmatched agents that reached their destination.
        Returns True if the set of matches changed."""
        finished = [s for s in self.matches_sim_list if s.phase == Phase.DONE]
        for sim in finished:
            self.matches_sim_list.remove(sim)
            w_rid = self.agent_id_to_request_id.pop(sim.walker_agent.agent_id, None)
            if w_rid is not None:
                self.notify_status(w_rid, Status.DONE, match_id=sim.match_id)

            self.free_driver(sim)

        for lst in (self.driver_agent_list, self.walker_agent_list):
            for a in [a for a in lst if a.done]:
                lst.remove(a)
                rid = self.agent_id_to_request_id.pop(a.agent_id, None)
                if rid is not None:
                    self.notify_status(rid, Status.DONE, agent_id=a.agent_id)

        return bool(finished)

    # ---- one tick
    def step(self) -> None:
        routes_changed = False
        for req in drain_create_queue(self.app["create_q"]):
            try:
                if req.get("type") == "cancel":
                    self.cancel(req["request_id"])
                else:
                    self.handle_create_request(req)
            except Exception as e:  # e.g. OSRM down, bad coordinates
                traceback.print_exc()
                rid = req.get("request_id")
                if rid is not None:
                    self.notify_status(rid, Status.ERROR, message=str(e))
            routes_changed = True

        for a in self.driver_agent_list:
            a.update_position(self.t)
        for a in self.walker_agent_list:
            a.update_position(self.t)
        for sim in self.matches_sim_list:
            sim.update(self.t)

        if self.remove_finished():
            routes_changed = True

        data = build_snapshot_payload(
            t_s=self.t,
            sims=self.matches_sim_list,
            driver_agents=self.driver_agent_list,
            walker_agents=self.walker_agent_list,
            agent_id_to_request_id=self.agent_id_to_request_id,
            include_agent_id=True,
        )
        self.app["last_positions"] = data
        self.publish_all({"type": "positions", "data": data}, droppable=True)
        self._send(dispatch_frames_by_req_id(self.app, data))
        for rid, event in leftover_events(data, self.agent_id_to_request_id):
            self.publish_to(rid, event, droppable=True)

        if routes_changed:
            routes = build_routes_payload(self.matches_sim_list, version=self.t)
            self.app["routes"] = routes
            self.publish_all({"type": "routes", "data": routes})

        self.t += self.app["speed"]

    def run(self) -> None:
        self.publish_initial_state()
        while not self.stop_event.is_set():
            try:
                self.step()
            except Exception:  # never let one bad tick kill the simulation
                traceback.print_exc()
            time.sleep(config.TICK_SLEEP_S)


def start_simulation(app: web.Application, loop: asyncio.AbstractEventLoop) -> Simulation:
    sim = Simulation(app, loop)
    threading.Thread(target=sim.run, daemon=True).start()
    return sim
