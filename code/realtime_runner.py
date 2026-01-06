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


# Health check endpoint
async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def send_status(ws: web.WebSocketResponse, request_id: str, status: str):
    # Update the status in the in-memory storage
    create_requests[request_id]["status"] = status

    if ws.closed:
        return

    # Send the status update to the client
    await ws.send_str(json.dumps({
        "type": "status",
        "request_id": request_id,
        "status": status
    }))


async def worker_loop():
    while True:
        job = await create_q.get()
        request_id = job["request_id"]
        ws = job["ws"]
        data = job["data"]

        try:
            await send_status(ws, request_id, "processing")
            # Simulate processing time
            await asyncio.sleep(1.0)
            await send_status(ws, request_id, "completed")

        except Exception as e:
            create_requests[request_id]["status"] = "failed"
            await send_status(ws, request_id, "failed")


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
                "status": "created",
                "payload": payload
            }
            await ws.send_str(json.dumps({
                "type": "created",
                "request_id": request_id
            }))

            await ws.send_str(json.dumps({
                "type": "status",
                "request_id": request_id,
                "status": "queued"
            }))

            # Enqueue the job for processing
            await create_q.put({
                "request_id": request_id,
                "ws": ws,
                "data": payload
            })
            continue

        await ws.send_str(json.dumps({"type": "error", "msg": "Unknown message type"}))

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
