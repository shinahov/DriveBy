import asyncio
from typing import Any, Dict
from aiohttp import web


async def publish_by_id(app: web.Application, request_id: str, event: Dict[str, Any]) -> None:
    subs: Dict[str, set[web.WebSocketResponse]] = app["subscribers"]
    q: asyncio.Queue = app["pub_q_by_id"]

    if request_id not in subs:
        return

    # keep only latest event if queue is full
    if q.full():
        try:
            q.get_nowait()
            q.task_done()
        except asyncio.QueueEmpty:
            pass
    #print("publish_by_id", request_id, "subs?", request_id in subs, "qsize", q.qsize())
    #print("event:", event)
    await q.put((request_id, event))


async def send_status(app: web.Application, request_id: str, status: str, **extra) -> None:
    event = {"type": "status", "status": status, "request_id": request_id}
    event.update(extra)
    await publish_by_id(app, request_id, event)



async def publish(app: web.Application, event: Dict[str, Any]) -> None:
    q: asyncio.Queue = app["pub_q"]

    # keep only latest event if queue is full
    if q.full():
        try:
            q.get_nowait()
            q.task_done()
        except asyncio.QueueEmpty:
            pass

    await q.put(event)
