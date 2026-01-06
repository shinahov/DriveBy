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


async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="OK")


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

            async def simulate_processing(rid: str):
                await asyncio.sleep(0.5)
                create_requests[rid]["status"] = "processing"
                if ws.closed:
                    return
                await ws.send_str(json.dumps({
                    "type": "status",
                    "request_id": rid,
                    "status": create_requests[rid]["status"]
                }))
                await asyncio.sleep(1.0)
                create_requests[rid]["status"] = "completed"
                await ws.send_str(json.dumps({
                    "type": "status",
                    "request_id": rid,
                    "status": create_requests[rid]["status"]
                }))
            asyncio.create_task(simulate_processing(request_id))
            continue

    return ws


def create_app() -> web.Application:
    app = web.Application()
    app.add_routes([
        web.get('/health', health_check),
        web.get('/ws', ws_handler)
    ])
    return app


if __name__ == "__main__":
    app = create_app()
    web.run_app(app, host="127.0.0.1", port=8000)
