// All status values the server sends ({type: "status", status: ...}).
// Same values as status.py on the server.
const Status = Object.freeze({
    QUEUED: "queued",
    SUBSCRIBED: "subscribed",
    NOT_MATCHED: "not_matched",
    MATCHED: "matched",
    DONE: "done",
    ERROR: "error",
    CANCELLED: "cancelled",
    UNKNOWN: "unknown",
});

// Phase of a match, sent in every position frame (frame.phase).
// Same names as Phase in MatchSimulation.py.
const Phase = Object.freeze({
    WALK_TO_PICKUP: "WALK_TO_PICKUP",
    WAIT_AT_PICKUP: "WAIT_AT_PICKUP",
    RIDE_WITH_DRIVER: "RIDE_WITH_DRIVER",
    WALK_FROM_DROPOFF: "WALK_FROM_DROPOFF",
    DONE: "DONE",
});
