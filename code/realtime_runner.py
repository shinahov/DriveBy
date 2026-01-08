import asyncio
import json
import uuid
from queue import Queue
from dataclasses import dataclass, field
from typing import Any, Dict, Set

from pathlib import Path
from aiohttp import web, WSMsgType

from local_osrm import start_simulation


def create_uuid() -> str:
    return str(uuid.uuid4())


# In-memory storage for requests
create_requests: Dict[str, Dict[str, Any]] = {}
# async job queue for create requests
create_q: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

# for status subscriptions
subscribers: Dict[str, Set[web.WebSocketResponse]] = {}

ws_clients: Set[web.WebSocketResponse] = set()


async def publish(app: web.Application, event: Dict[str, Any]):
    q: asyncio.Queue = app["pub_q"]

    if q.full():
        try:
            q.get_nowait()
            q.task_done()
        except asyncio.QueueEmpty:
            pass
    await q.put(event)

async def broadcaster(app: web.Application):
    q: asyncio.Queue = app["pub_q"]
    while True:
        evnt = await q.get()
        msg = json.dumps(evnt)

        dead_clients = set()
        for ws in ws_clients:
            if ws.closed:
                dead_clients.add(ws)
                continue
            try:
                await ws.send_str(msg)
            except Exception:
                dead_clients.add(ws)

        for ws in dead_clients:
            ws_clients.discard(ws)

        q.task_done()

# Health check endpoint
async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="OK")


# Add a subscriber for a specific request_id
def add_subscriber(request_id: str, ws: web.WebSocketResponse):
    if request_id not in subscribers:
        subscribers[request_id] = set()
    subscribers[request_id].add(ws)


# Remove a subscriber from all request_id sets
def remove_subscriber_everywhere(ws: web.WebSocketResponse) -> None:
    # Remove ws from all request_id subscriber sets
    empty = []
    for rid, conns in subscribers.items():
        conns.discard(ws)
        if not conns:
            empty.append(rid)
    # Cleanup empty sets
    for rid in empty:
        del subscribers[rid]


async def broadcast_status(request_id: str, status: str):
    create_requests[request_id]["status"] = status
    msg = json.dumps({
        "type": "status",
        "request_id": request_id,
        "status": status
    })

    conns = subscribers.get(request_id, set())
    if not conns:
        return

    dead_conns = set()
    for ws in conns:
        if ws.closed:
            dead_conns.add(ws)
            continue
        try:
            await ws.send_str(msg)
        except Exception:
            dead_conns.add(ws)
    for ws in dead_conns:
        conns.discard(ws)


async def worker_loop():
    while True:
        job = await create_q.get()
        request_id = job["request_id"]
        data = job["data"]

        try:
            await broadcast_status(request_id, "processing")
            # Simulate processing time
            await asyncio.sleep(1.0)
            await broadcast_status(request_id, "completed")

        except Exception as e:
            create_requests[request_id]["status"] = "failed"
            await broadcast_status(request_id, "failed")

        # Mark the task as done
        finally:
            create_q.task_done()


# WebSocket handler
async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)

    ws_clients.add(ws)

    try:
        await ws.send_str(json.dumps({
            "type": "hello",
            "msg": "Welcome to the WebSocket server!"
        }))

        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue

            try:
                data = json.loads(msg.data)
            except json.JSONDecodeError:
                await ws.send_str(json.dumps({"type": "error", "msg": "Invalid JSON"}))
                continue

            if data.get("type") == "create_request":
                request_id = create_uuid()
                payload = data.get("payload", {})

                create_requests[request_id] = {"status": "queued", "payload": payload}


                request.app["create_q"].put({
                    "request_id": request_id,
                    "payload": payload
                })

                add_subscriber(request_id, ws)

                await ws.send_str(json.dumps({"type": "created", "request_id": request_id}))
                await broadcast_status(request_id, "queued")


                # await create_q.put({"request_id": request_id, "data": payload})

                continue

            if data.get("type") == "subscribe":
                rid = data.get("request_id")
                if not rid:
                    await ws.send_str(json.dumps({"type": "error", "msg": "missing request_id"}))
                    continue

                add_subscriber(rid, ws)

                st = create_requests.get(rid, {"status": "unknown"})
                await ws.send_str(json.dumps({
                    "type": "status",
                    "request_id": rid,
                    "status": st.get("status", "unknown")
                }))
                continue

            await ws.send_str(json.dumps({"type": "error", "msg": "Unknown message type"}))

    finally:
        ws_clients.discard(ws)
        remove_subscriber_everywhere(ws)

    return ws



# Startup task to run the worker loop
async def on_startup(app: web.Application):
    app['pub_q'] = asyncio.Queue(maxsize=1)
    app['broadcaster_task'] = asyncio.create_task(broadcaster(app))
    app["create_q"] = Queue()

    loop = asyncio.get_running_loop()
    start_simulation(app, loop)


# Cleanup on shutdown
async def on_cleanup(app: web.Application):
    app['worker_task'].cancel()
    try:
        await app['worker_task']
    except asyncio.CancelledError:
        pass


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"


async def index(request: web.Request) -> web.StreamResponse:
    return web.FileResponse(WEB_DIR / "map.html")


@web.middleware
async def no_cache(request, handler):
    resp = await handler(request)
    if isinstance(resp, web.StreamResponse):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp

def create_app() -> web.Application:
    app = web.Application(middlewares=[no_cache])
    app.add_routes([
        web.get("/", index),
        web.get("/health", health_check),
        web.get("/ws", ws_handler),
    ])

    # Serve static files
    app.router.add_static("/web/", path=str(WEB_DIR), show_index=True)

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app



if __name__ == "__main__":
    app = create_app()
    web.run_app(app, host="127.0.0.1", port=8000)

