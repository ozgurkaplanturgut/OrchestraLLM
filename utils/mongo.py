# utils/mongo.py
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from pymongo import MongoClient, ASCENDING, ReturnDocument
from pymongo.errors import OperationFailure
from utils.config import settings

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
            convs.create_index([("user_id", ASCENDING), ("session_id", ASCENDING)],
                               name="conv_user_session", unique=True)
        if "updated_at" not in convs.index_information():
            convs.create_index([("updated_at", ASCENDING)], name="updated_at")
        if "state_ctx_user_session" not in app_states.index_information():
            app_states.create_index(
                [("context", ASCENDING), ("user_id", ASCENDING),
                 ("session_id", ASCENDING), ("updated_at", ASCENDING)],
                name="state_ctx_user_session"
            )
    except OperationFailure:
        # indeks var ise sorun değil
        pass

def _next_sequence_for_task(task_id: str) -> int:
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
    Geriye dönük uyum:
      - Yeni imza: save_stream_event(event_dict)
      - Eski imza: save_stream_event(task_id, typ, **fields)

    DÖNEN dict en az {task_id, type} içerir; kwargs event’e eklenir.
    """
    # Yeni imza: tek argüman dict
    if len(args) == 1 and isinstance(args[0], dict):
        ev = dict(args[0])  # kopya
        # Eski kod 'typ' anahtarı ile göndermiş olabilir → 'type'a çevir
        if "type" not in ev and "typ" in ev:
            ev["type"] = ev.pop("typ")
        return ev

    # Eski imza: (task_id, typ, **fields)
    if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], str):
        task_id: str = args[0]
        typ: str = args[1]
        ev: Dict[str, Any] = {"task_id": task_id, "type": typ}
        # args[2:] için bir şey beklemiyoruz; tüm ekstra alanlar kwargs ile gelmeli
        ev.update(kwargs or {})
        return ev

    # Beklenmedik durum: yine de kwargs’tan üretmeye çalış
    if "task_id" in kwargs and ("type" in kwargs or "typ" in kwargs):
        ev = dict(kwargs)
        if "type" not in ev and "typ" in ev:
            ev["type"] = ev.pop("typ")
        return ev

    raise TypeError("save_stream_event: invalid arguments. Use event dict or (task_id, typ, **fields).")

def save_stream_event(*args, **kwargs) -> Dict[str, Any]:
    """
    Event’i 'streams' koleksiyonuna kalıcı yazar.
    İmza uyumlu: save_stream_event(event_dict) veya save_stream_event(task_id, typ, **fields)
    Otomatik olarak 'seq' ve 'created_at' eklenir.
    """
    db = get_db()
    ev = _normalize_event_args(*args, **kwargs)

    if "task_id" not in ev:
        raise ValueError("save_stream_event: 'task_id' zorunludur.")
    if "type" not in ev:
        raise ValueError("save_stream_event: 'type' zorunludur.")

    if "seq" not in ev:
        ev["seq"] = _next_sequence_for_task(ev["task_id"])
    if "created_at" not in ev:
        ev["created_at"] = time.time()

    db.streams.insert_one(ev)
    return ev