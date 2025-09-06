from __future__ import annotations

import time
from typing import Any, Dict, Optional

from pymongo import MongoClient, ASCENDING, ReturnDocument
from pymongo.errors import OperationFailure
from orchestrallm.shared.config.settings import settings

_client: Optional[MongoClient] = None
_db = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(settings.MONGODB_URI)
    return _client


def get_db():
    global _db
    if _db is None:
        _db = get_client()[settings.MONGODB_DB]
    return _db


def ensure_indexes() -> None:
    """Create indexes for collections if they do not exist."""
    db = get_db()
    tasks = db.get_collection("tasks")
    streams = db.get_collection("streams")
    convs = db.get_collection("conversations")
    app_states = db.get_collection("app_states")
    try:
        if "task_id_unique" not in tasks.index_information():
            tasks.create_index([("task_id", ASCENDING)], name="task_id_unique", unique=True)
        if "task_seq" not in streams.index_information():
            streams.create_index([("task_id", ASCENDING), ("seq", ASCENDING)], name="task_seq")
        if "created_at" not in streams.index_information():
            streams.create_index([("created_at", ASCENDING)], name="created_at")
        if "conv_user_session" not in convs.index_information():
            convs.create_index(
                [("user_id", ASCENDING), ("session_id", ASCENDING)],
                name="conv_user_session",
                unique=True,
            )
        if "updated_at" not in convs.index_information():
            convs.create_index([("updated_at", ASCENDING)], name="updated_at")
        if "state_ctx_user_session" not in app_states.index_information():
            app_states.create_index(
                [
                    ("context", ASCENDING),
                    ("user_id", ASCENDING),
                    ("session_id", ASCENDING),
                    ("updated_at", ASCENDING),
                ],
                name="state_ctx_user_session",
            )
    except OperationFailure:
        pass


def _next_sequence_for_task(task_id: str) -> int:
    """Generate the next incremental sequence number for a given task_id."""
    db = get_db()
    doc = db.counters.find_one_and_update(
        {"_id": f"streams:{task_id}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc.get("seq", 1))


def _normalize_event_args(*args, **kwargs) -> Dict[str, Any]:
    """
    Backward compatibility:
      - New signature: save_stream_event(event_dict)
      - Old signature: save_stream_event(task_id, typ, **fields)

    Returned dict contains at least {task_id, type}; kwargs are merged into the event.
    """
    if len(args) == 1 and isinstance(args[0], dict):
        ev = dict(args[0])
        if "type" not in ev and "typ" in ev:
            ev["type"] = ev.pop("typ")
        return ev

    if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], str):
        task_id: str = args[0]
        typ: str = args[1]
        ev: Dict[str, Any] = {"task_id": task_id, "type": typ}
        ev.update(kwargs or {})
        return ev

    if "task_id" in kwargs and ("type" in kwargs or "typ" in kwargs):
        ev = dict(kwargs)
        if "type" not in ev and "typ" in ev:
            ev["type"] = ev.pop("typ")
        return ev

    raise TypeError("save_stream_event: invalid arguments. Use event dict or (task_id, typ, **fields).")


def save_stream_event(*args, **kwargs) -> Dict[str, Any]:
    """
    Persist an event to the 'streams' collection.
    Compatible signatures:
      - save_stream_event(event_dict)
      - save_stream_event(task_id, typ, **fields)

    Automatically adds 'seq' and 'created_at' fields.
    """
    db = get_db()
    ev = _normalize_event_args(*args, **kwargs)

    if "task_id" not in ev:
        raise ValueError("save_stream_event: 'task_id' is required.")
    if "type" not in ev:
        raise ValueError("save_stream_event: 'type' is required.")

    if "seq" not in ev:
        ev["seq"] = _next_sequence_for_task(ev["task_id"])
    if "created_at" not in ev:
        ev["created_at"] = time.time()

    db.streams.insert_one(ev)
    return ev
