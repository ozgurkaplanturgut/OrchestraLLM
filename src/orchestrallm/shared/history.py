from __future__ import annotations
import time
from typing import List, Dict, Optional

from pymongo import MongoClient, ASCENDING, IndexModel
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError
from pymongo.errors import OperationFailure

from orchestrallm.shared.config.settings import settings
from orchestrallm.shared.persistence.mongo import get_db

MONGO_URI: str = getattr(settings, "MONGODB_URI", "mongodb://localhost:27017")
MONGO_DB: str = getattr(settings, "MONGODB_DB", "ragchat")
COLL_NAME: str = getattr(settings, "CONVERSATIONS_COLLECTION", "conversations")
MAX_MESSAGES: int = getattr(settings, "HISTORY_MAX_MESSAGES", 200)

_coll: Optional[Collection] = None


def _get_coll():
    global _coll
    if _coll is None:
        _coll = get_db().get_collection("conversations")

        try:
            info = _coll.index_information()
            if "conv_user_session" not in info:
                _coll.create_indexes([
                    IndexModel(
                        [("user_id", ASCENDING), ("session_id", ASCENDING)],
                        name="conv_user_session",
                        unique=True,
                    )
                ])
        except OperationFailure as e:
            if e.code != 85:
                raise
    return _coll


def _now_ts() -> float:
    return time.time()


def load_history(*, user_id: str, session_id: str, limit: int = 10) -> List[Dict[str, str]]:
    """
    This loads the last `limit` messages for the given user_id and session_id.
    """
    coll = _get_coll()
    doc = coll.find_one(
        {"user_id": user_id, "session_id": session_id},
        {"_id": 0, "messages": {"$slice": -int(max(1, limit))}},
    )
    msgs = (doc or {}).get("messages", []) or []
    out: List[Dict[str, str]] = []
    for m in msgs:
        role = m.get("role")
        content = m.get("content")
        if role and content:
            out.append({"role": role, "content": content})
    return out


def append_message(*, user_id: str, session_id: str, role: str, content: str) -> None:
    """
    This appends a message to the conversation history for the given user_id and session_id.
    """
    coll = _get_coll()

    msg_doc = {
        "role": role,
        "content": content,
        "ts": _now_ts(),
    }

    try:
        coll.update_one(
            {"user_id": user_id, "session_id": session_id},
            {
                "$setOnInsert": {
                    "user_id": user_id,
                    "session_id": session_id,
                    "created_at": _now_ts(),
                },
                "$push": {
                    "messages": {
                        "$each": [msg_doc],
                        "$slice": -int(MAX_MESSAGES),
                    }
                },
                "$set": {
                    "updated_at": _now_ts(),
                },
            },
            upsert=True,
        )
    except DuplicateKeyError:
        coll.update_one(
            {"user_id": user_id, "session_id": session_id},
            {
                "$push": {
                    "messages": {
                        "$each": [msg_doc],
                        "$slice": -int(MAX_MESSAGES),
                    }
                },
                "$set": {"updated_at": _now_ts()},
            },
            upsert=False,
        )