from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from orchestrallm.shared.persistence.mongo import save_stream_event

class InProcEventBus:
    def __init__(self) -> None:
        self._subs: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, task_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        async with self._lock:
            self._subs.setdefault(task_id, []).append(q)
        return q

    async def unsubscribe(self, task_id: str, q: asyncio.Queue) -> None:
        async with self._lock:
            lst = self._subs.get(task_id, [])
            if q in lst:
                lst.remove(q)
            if not lst and task_id in self._subs:
                self._subs.pop(task_id, None)

    async def publish(self, ev: Dict[str, Any]) -> None:
        task_id = ev.get("task_id")
        if not task_id:
            return
        async with self._lock:
            queues = list(self._subs.get(task_id, []))
        for q in queues:
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:
                pass

EVENT_BUS = InProcEventBus()


def _normalize_event_shape(event: Any) -> Dict[str, Any]:
    if not isinstance(event, dict):
        return {"type": "info", "message": str(event)}

    ev = dict(event)  
    if "type" not in ev:
        if "typ" in ev:
            ev["type"] = ev.pop("typ")
        elif "event" in ev:
            ev["type"] = ev.pop("event")
        elif "name" in ev:
            ev["type"] = ev.pop("name")

    if "type" not in ev:
        if "content" in ev:
            ev["type"] = "token"
        elif "message" in ev:
            ev["type"] = "status"
        else:
            ev["type"] = "info"

    return ev

async def publish_event_async(event: Any) -> Dict[str, Any]:
    ev = _normalize_event_shape(event)

    if "task_id" not in ev or not ev["task_id"]:
        raise ValueError("publish_event_async: 'task_id' is required in event")

    saved = save_stream_event(ev)  
    await EVENT_BUS.publish(saved)  
    return saved


async def send_status(task_id: str, message: str) -> Dict[str, Any]:
    return await publish_event_async({"task_id": task_id, "type": "status", "message": message})

async def send_token(task_id: str, content: str) -> Dict[str, Any]:
    return await publish_event_async({"task_id": task_id, "type": "token", "content": content})

async def send_error(task_id: str, message: str) -> Dict[str, Any]:
    return await publish_event_async({"task_id": task_id, "type": "error", "message": message})

async def send_done(task_id: str) -> Dict[str, Any]:
    return await publish_event_async({"task_id": task_id, "type": "done"})
