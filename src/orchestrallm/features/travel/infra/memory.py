# app/travel/memory.py
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from utils.mongo import get_db

_CONTEXT = "travel"
_META_KEYS = {"_id", "context", "user_id", "session_id", "updated_at"}


def _normalize_state(state: Optional[Dict[str, Any]], kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """
    This normalizes the state to be saved.
    If state is None, it tries to extract from kwargs.
    """
    if state is None:
        if "payload" in kwargs and isinstance(kwargs["payload"], dict):
            state = dict(kwargs["payload"])
        else:
            # user_id / session_id / context dışındaki tüm kwargs'ı state olarak al
            state = {k: v for k, v in kwargs.items() if k not in {"user_id", "session_id", "context"}}

    if not isinstance(state, dict):
        # Beklenmedik tip gelirse sarmala
        state = {"value": state}
    return state


def save_travel_state(user_id: str, session_id: str, state: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
    """
    This saves the travel state for the given user_id and session_id.
    """
    db = get_db()
    payload = _normalize_state(state, kwargs)

    now = time.time()
    # meta ve state'leri tek düzlemde saklıyoruz (okuma kolaylığı için)
    set_doc: Dict[str, Any] = dict(payload)
    set_doc["updated_at"] = now

    db.app_states.update_one(
        {"context": _CONTEXT, "user_id": user_id, "session_id": session_id},
        {"$set": set_doc, "$setOnInsert": {"context": _CONTEXT, "user_id": user_id, "session_id": session_id}},
        upsert=True,
    )
    return set_doc


def load_last_state(user_id: str, session_id: str) -> Dict[str, Any]:
    """
    This loads the last travel state for the given user_id and session_id.
    """
    db = get_db()
    doc = db.app_states.find_one({"context": _CONTEXT, "user_id": user_id, "session_id": session_id})
    if not doc:
        return {}
    return {k: v for k, v in doc.items() if k not in _META_KEYS}
