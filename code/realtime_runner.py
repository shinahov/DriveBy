import json
import time
import threading
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

def start_server(port: int = 8000):
    server = ThreadingHTTPServer(("127.0.0.1", port), SimpleHTTPRequestHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

def write_positions(t_s: float, walker_pos, driver_positions):
    data = {
        "t_s": t_s,
        "walker": {"lat": walker_pos[0], "lon": walker_pos[1]},
        "drivers": [{"lat": p[0], "lon": p[1]} for p in driver_positions],
    }
    with open("positions.json", "w", encoding="utf-8") as f:
        json.dump(data, f)

def main():
    start_server(8000)
    webbrowser.open("http://127.0.0.1:8000/map.html")

    # Dummy movement
    t = 0.0
    dt = 0.2  # 5 Hz
    base_walker = (51.202561, 6.780486)
    base_driver = (51.2562, 7.1508)

    while True:
        walker_pos = (base_walker[0], base_walker[1] + 0.0005 * (t / 5.0))
        driver_positions = [
            (base_driver[0], base_driver[1] - 0.0005 * (t / 5.0)),
            (base_driver[0] + 0.003, base_driver[1] - 0.0003 * (t / 5.0)),
        ]

        write_positions(t, walker_pos, driver_positions)
        time.sleep(dt)
        t += dt

if __name__ == "__main__":
    main()
