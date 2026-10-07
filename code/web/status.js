// All status values the server sends ({type: "status", status: ...}).
// Same values as status.py on the server.
const Status = Object.freeze({
    QUEUED: "queued",
    SUBSCRIBED: "subscribed",
    NOT_MATCHED: "not_matched",
    MATCHED: "matched",
    DONE: "done",
    ERROR: "error",
});
