import json
import uuid
import os
import tempfile
import threading
import time
from queue import Queue
from urllib.parse import urlparse, parse_qs
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler


def create_uuid():
    return str(uuid.uuid4())


def make_handler(q: Queue):
    class MyHandler(SimpleHTTPRequestHandler):
        speed = 0.2
        my_queue = q  # shared
        create_requests = {}

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

            if self.path.startswith("/speed"):
                qs = parse_qs(urlparse(self.path).query)
                v = qs.get("value", [None])[0]
                try:
                    if v is None:
                        raise ValueError("missing value")
                    MyHandler.speed = max(0.001, float(v))
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"OK")
                except Exception as e:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(str(e).encode("utf-8"))
                return

            if self.path.startswith("/create_status"):
                qs = parse_qs(urlparse(self.path).query)
                rid = qs.get("request_id", [None])[0]

                if not rid:
                    self.send_response(400)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"missing request_id")
                    return

                st = MyHandler.create_requests.get(rid, {"status": "unknown"})

                body = json.dumps(st).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
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
                requests_id = create_uuid()
                MyHandler.my_queue.put({
                    "request_id": requests_id,
                    "payload": payload})
                MyHandler.create_requests[requests_id] = {"status": "queued"}
                body = json.dumps({"request_id": requests_id}).encode("utf-8")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

            except Exception as e:
                body = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)



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
