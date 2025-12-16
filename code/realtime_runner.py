import json
import os
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

def start_server(port: int = 8000):
    server = ThreadingHTTPServer(("127.0.0.1", port), SimpleHTTPRequestHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

def write_positions_json(data, filename="positions.json", retries=30, sleep_s=0.01):
    dir_name = os.path.dirname(os.path.abspath(filename)) or "."
    last_err = None

    for _ in range(retries):
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="pos_", suffix=".json", dir=dir_name)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_path, filename)
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
