"""All status values the server sends to the browser ({"type": "status", "status": ...}).
Keep in sync with web/status.js (tests/test_status.py checks that)."""
from enum import Enum


class Status(str, Enum):
    # str + Enum: Status.MATCHED == "matched" and json.dumps writes "matched"
    QUEUED = "queued"            # request received, waiting for the simulation
    SUBSCRIBED = "subscribed"    # page (re)subscribed to its request_id
    NOT_MATCHED = "not_matched"  # agent exists, no partner yet
    MATCHED = "matched"          # agent got a partner
    DONE = "done"                # trip / route finished
    ERROR = "error"              # request failed (e.g. OSRM down)
    UNKNOWN = "unknown"          # subscribe to a request_id the server does not know (e.g. after a restart)
