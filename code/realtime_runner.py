import json
import os
import tempfile
import threading
import time
from queue import Queue
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler


def make_handler(q: Queue):
    class MyHandler(SimpleHTTPRequestHandler):
        speed = 0.2
        my_queue = q  # shared

        def end_headers(self):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            super().end_headers()

        def do_GET(self):
            if self.path == "/faster":
                MyHandler.speed += 0.05
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
                return

            if self.path == "/slower":
                MyHandler.speed = max(0.001, MyHandler.speed - 0.05)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
                return

            return super().do_GET()

        def do_POST(self):
            if self.path != "/create_agent":
                self.send_response(404, message="Non implemented yet")
                self.end_headers()
                return

            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)

            try:
                payload = json.loads(raw.decode("utf-8"))
                MyHandler.my_queue.put(payload)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")

            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(str(e).encode("utf-8"))



    return MyHandler


def start_server(create_q: Queue, port: int = 8000):
    handler_cls = make_handler(create_q)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return handler_cls

def write_positions_json(data, filename="positions.json", retries=30, sleep_s=0.01):
    path = os.path.join("web", filename)
    dir_name = os.path.dirname(os.path.abspath(path)) or "."
    last_err = None

    for _ in range(retries):
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="pos_", suffix=".json", dir=dir_name)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_path, path)
            return
        except PermissionError as e:
            last_err = e
            time.sleep(sleep_s)
        finally:
            if tmp_path is not None:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    raise last_err
