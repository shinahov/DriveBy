import asyncio
from typing import Any, Dict

from aiohttp import web

# Events marked droppable (positions, sent many times per second) are skipped
# when this many messages are already waiting. Everything else (status, routes)
# is never dropped.
MAX_BACKLOG = 10


def _should_drop(q: asyncio.Queue, droppable: bool) -> bool:
    return droppable and q.qsize() >= MAX_BACKLOG


async def publish_by_id(app: web.Application, request_id: str, event: Dict[str, Any],
                        droppable: bool = False) -> None:
    """Send event to everyone subscribed to request_id."""
    if request_id not in app["subscribers"]:
        return
    q: asyncio.Queue = app["pub_q_by_id"]
    if _should_drop(q, droppable):
        return
    await q.put((request_id, event))


async def send_status(app: web.Application, request_id: str, status: str, **extra) -> None:
    event = {"type": "status", "status": status, "request_id": request_id}
    event.update(extra)
    remember_status(app, request_id, event)
    await publish_by_id(app, request_id, event)


def remember_status(app: web.Application, request_id: str, event: Dict[str, Any]) -> None:
    """Keep the newest status per request, so a reloaded page can get it again."""
    last = app.get("last_status_by_req")
    if last is not None:
        last[request_id] = event


async def publish(app: web.Application, event: Dict[str, Any], droppable: bool = False) -> None:
    """Send event to all clients of the global /ws (the overview map)."""
    q: asyncio.Queue = app["pub_q"]
    if _should_drop(q, droppable):
        return
    await q.put(event)
