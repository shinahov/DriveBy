"""
Fake OSRM for tests: answers /route/v1/<profile>/<lon,lat;lon,lat> requests
with a straight line between the two points, without Docker or network.

Usage:
    with fake_osrm():
        ... code that calls requests.get / requests.Session.get ...
"""
import math
import re
from contextlib import contextmanager
from unittest import mock

import requests

SPEED_M_S = {"driving": 12.0, "walking": 1.4}
STEP_M = 40.0  # distance between geometry points

_URL_RE = re.compile(r"/route/v1/(\w+)/([-\d.]+),([-\d.]+);([-\d.]+),([-\d.]+)")


def _haversine_m(a, b):
    R = 6371000.0
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    x = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(x))


def route_response(profile, start, dest):
    """OSRM-shaped JSON for a straight line start -> dest (lat, lon tuples)."""
    total = _haversine_m(start, dest)
    n = max(1, int(math.ceil(total / STEP_M)))
    pts = [(start[0] + (dest[0] - start[0]) * i / n,
            start[1] + (dest[1] - start[1]) * i / n) for i in range(n + 1)]
    seg_d = [_haversine_m(pts[i], pts[i + 1]) for i in range(n)]
    seg_t = [d / SPEED_M_S[profile] for d in seg_d]
    return {
        "code": "Ok",
        "routes": [{
            "distance": sum(seg_d),
            "duration": sum(seg_t),
            "geometry": {"type": "LineString",
                         "coordinates": [[lon, lat] for lat, lon in pts]},
            "legs": [{"annotation": {"distance": seg_d,
                                     "duration": seg_t,
                                     "nodes": list(range(n + 1))}}],
        }],
    }


class _Resp:
    def __init__(self, data):
        self._data = data
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def _fake_get(url, *args, **kwargs):
    m = _URL_RE.search(url)
    if not m:
        raise AssertionError(f"unexpected URL in test: {url}")
    profile = m.group(1)
    lon1, lat1, lon2, lat2 = map(float, m.groups()[1:])
    return _Resp(route_response(profile, (lat1, lon1), (lat2, lon2)))


def _fake_session_get(self, url, *args, **kwargs):
    return _fake_get(url, *args, **kwargs)


def _clear_route_caches():
    # lru_caches in the project would otherwise keep results between tests
    import os
    import sys
    code_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for mod in list(sys.modules.values()):
        f = os.path.abspath(getattr(mod, "__file__", None) or "")
        if os.path.dirname(f) != code_dir:
            continue
        for v in list(vars(mod).values()):
            if callable(v) and hasattr(v, "cache_clear") and hasattr(v, "cache_info"):
                v.cache_clear()


@contextmanager
def fake_osrm():
    _clear_route_caches()
    with mock.patch.object(requests, "get", _fake_get), \
         mock.patch.object(requests.Session, "get", _fake_session_get):
        yield
    _clear_route_caches()
