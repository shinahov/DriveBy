"""Start the server:  py main.py   then open http://127.0.0.1:8000
(OSRM must be running first: start_osrm.bat)"""
from aiohttp import web

import config
from server import create_app


def main():
    print(f"Server: http://{config.HOST}:{config.PORT}")
    web.run_app(create_app(), host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
