"""Backend and frontend (web/status.js) must know the same statuses and phases."""
import json
import os
import re
import sys
import unittest

CODE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CODE)

from MatchSimulation import Phase  # noqa: E402
from status import Status  # noqa: E402


def js_object(name):
    """{KEY: "value"} of `const <name> = Object.freeze({...})` in web/status.js"""
    with open(os.path.join(CODE, "web", "status.js"), encoding="utf-8") as f:
        block = re.search(name + r" = Object\.freeze\(\{(.*?)\}\)", f.read(), re.S).group(1)
    return dict(re.findall(r'([A-Z_]+):\s*"(\w+)"', block))


class StatusTests(unittest.TestCase):
    def test_same_values_in_python_and_js(self):
        self.assertEqual(js_object("Status"), {s.name: s.value for s in Status})

    def test_same_phases_in_python_and_js(self):
        # the server sends phase.name (payloads.py)
        self.assertEqual(js_object("Phase"), {p.name: p.name for p in Phase})

    def test_is_a_plain_string_in_json(self):
        self.assertEqual(json.dumps({"status": Status.MATCHED}), '{"status": "matched"}')
        self.assertEqual(Status.MATCHED, "matched")


if __name__ == "__main__":
    unittest.main()
