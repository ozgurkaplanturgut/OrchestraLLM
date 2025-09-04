from __future__ import annotations

import asyncio
import json
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from orchestrallm.shared.eventbus.events import EVENT_BUS, publish_event_async
from orchestrallm.shared.persistence.mongo import get_db

router = APIRouter(tags=["stream"])

def _ws_send_json(ws: WebSocket, obj: dict):
    return ws.send_text(json.dumps(obj, ensure_ascii=False, default=str))

@router.websocket("/stream/{task_id}")
async def stream_ws(ws: WebSocket, task_id: str, from_seq: Optional[int] = Query(default=None)):
    await ws.accept()
    db = get_db()
    last_seq = int(from_seq) if from_seq is not None else 0

    # 1) backfill
    for ev in db.streams.find({"task_id": task_id, "seq": {"$gt": last_seq}}).sort("seq", 1):
        s = int(ev.get("seq", 0))
        if s > last_seq:
            last_seq = s
            await _ws_send_json(ws, ev)

    # 2) canlı event'ler
    q = await EVENT_BUS.subscribe(task_id)

    async def pump_bus():
        nonlocal last_seq
        try:
            while True:
                ev = await q.get()
                s = int(ev.get("seq", 0))
                if s > last_seq:
                    last_seq = s
                    await _ws_send_json(ws, ev)
        except Exception:
            pass

    async def pump_db():
        nonlocal last_seq
        try:
            while True:
                cur = db.streams.find({"task_id": task_id, "seq": {"$gt": last_seq}}).sort("seq", 1)
                for ev in cur:
                    s = int(ev.get("seq", 0))
                    if s > last_seq:
                        last_seq = s
                        await _ws_send_json(ws, ev)
                await asyncio.sleep(0.25)
        except Exception:
            pass

    t1 = asyncio.create_task(pump_bus())
    t2 = asyncio.create_task(pump_db())
    try:
        await asyncio.gather(t1, t2)
    except WebSocketDisconnect:
        pass
    finally:
        t1.cancel(); t2.cancel()
        await EVENT_BUS.unsubscribe(task_id, q)
