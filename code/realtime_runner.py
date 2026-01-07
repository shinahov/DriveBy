import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Set

from aiohttp import web, WSMsgType


def create_uuid() -> str:
    return str(uuid.uuid4())


# In-memory storage for requests
create_requests: Dict[str, Dict[str, Any]] = {}
# async job queue for create requests
create_q: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

# for status subscriptions
subscribers: Dict[str, Set[web.WebSocketResponse]] = {}

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

    await ws.send_str(
        json.dumps({"type": "hello", "msg": "Welcome to the WebSocket server!"}))

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
            create_requests[request_id] = {
                "status": "queued",
                "payload": payload
            }
            add_subscriber(request_id, ws)

            await ws.send_str(json.dumps({
                "type": "created",
                "request_id": request_id
            }))
            await broadcast_status(request_id, "queued")

            # Enqueue the job for processing
            await create_q.put({
                "request_id": request_id,
                "data": payload
            })
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
    remove_subscriber_everywhere(ws)
    return ws


# Startup task to run the worker loop
async def on_startup(app: web.Application):
    app['worker_task'] = asyncio.create_task(worker_loop())


# Cleanup on shutdown
async def on_cleanup(app: web.Application):
    app['worker_task'].cancel()
    try:
        await app['worker_task']
    except asyncio.CancelledError:
        pass

def create_app() -> web.Application:
    app = web.Application()
    app.add_routes([
        web.get('/health', health_check),
        web.get('/ws', ws_handler)
    ])
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


if __name__ == "__main__":
    app = create_app()
    web.run_app(app, host="127.0.0.1", port=8000)
