"""Backend (status.py) and frontend (web/status.js) must know the same statuses."""
import json
import os
import re
import sys
import unittest

CODE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CODE)

from status import Status  # noqa: E402


class StatusTests(unittest.TestCase):
    def test_same_values_in_python_and_js(self):
        with open(os.path.join(CODE, "web", "status.js"), encoding="utf-8") as f:
            js = dict(re.findall(r'([A-Z_]+):\s*"(\w+)"', f.read()))
        py = {s.name: s.value for s in Status}
        self.assertEqual(js, py)

    def test_is_a_plain_string_in_json(self):
        self.assertEqual(json.dumps({"status": Status.MATCHED}), '{"status": "matched"}')
        self.assertEqual(Status.MATCHED, "matched")


if __name__ == "__main__":
    unittest.main()
