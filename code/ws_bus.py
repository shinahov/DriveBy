import asyncio
from typing import Any, Dict
from aiohttp import web

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
