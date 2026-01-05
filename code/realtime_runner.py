import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Set

from aiohttp import web, WSMsgType


def create_uuid() -> str:
    return str(uuid.uuid4())


async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="OK")


def create_app() -> web.Application:
    app = web.Application()
    app.add_routes([
        web.get('/health', health_check)
    ])
    return app


if __name__ == "__main__":
    app = create_app()
    web.run_app(app, host="127.0.0.1", port=8000)
