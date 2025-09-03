# api_service.py
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from utils.config import settings
from utils.logger import setup_logging
from utils.mongo import get_db, ensure_indexes
from utils.events import EVENT_BUS, publish_event_async
from utils.data_classes import (
    ChatPayload,
    IngestPayload,
    RagPayload,
    TravelPayload,
    RecipePayload
)

from app.tasks.chat_tasks import run_chat_task
from app.tasks.ingest_tasks import run_ingest_task
from app.tasks.rag_tasks import run_rag_task
from app.tasks.recipe_tasks import run_recipe_task
from app.travel.agno_team import stream_travel_plan

def _ws_send_json(ws: WebSocket, obj: dict):
    return ws.send_text(json.dumps(obj, ensure_ascii=False, default=str))

setup_logging()
log = logging.getLogger("api")

app = FastAPI(title="RAGChat Async API", version="1.0.0")

allow_origins = (
    [o.strip() for o in settings.CORS_ALLOW_ORIGINS.split(",")]
    if settings.CORS_ALLOW_ORIGINS and settings.CORS_ALLOW_ORIGINS != "*"
    else ["*"]
)
allow_methods = (
    [m.strip() for m in settings.CORS_ALLOW_METHODS.split(",")]
    if settings.CORS_ALLOW_METHODS and settings.CORS_ALLOW_METHODS != "*"
    else ["*"]
)
allow_headers = (
    [h.strip() for h in settings.CORS_ALLOW_HEADERS.split(",")]
    if settings.CORS_ALLOW_HEADERS and settings.CORS_ALLOW_HEADERS != "*"
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=allow_methods,
    allow_headers=allow_headers,
)

@app.on_event("startup")
async def on_startup():
    ensure_indexes()
    workers = os.getenv("WEB_CONCURRENCY") or os.getenv("GUNICORN_WORKERS") or "auto"
    log.info(f"Startup complete. Gunicorn workers={workers} (EventBus process-scope; DB fallback enabled).")


@app.get("/health")
async def health():
    return {"ok": True, "t": time.time()}

@app.post("/v1/tasks/chat")
async def create_chat_task(payload: ChatPayload):
    task_id = str(uuid.uuid4())
    get_db().tasks.update_one(
        {"task_id": task_id},
        {"$set": {
            "type": "chat", "status": "queued",
            "user_id": payload.user_id, "session_id": payload.session_id,
            "created_at": time.time()}},
        upsert=True,
    )
    asyncio.create_task(_run_chat_wrapper(task_id, payload))
    return {"task_id": task_id, "status": "queued"}

async def _run_chat_wrapper(task_id: str, payload: ChatPayload):
    db = get_db()
    db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "running"}})
    try:
        await run_chat_task(task_id, payload.user_id, payload.session_id, payload.query)
        db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "done"}})
    except Exception as e:
        log.error("Chat task error", exc_info=True)
        db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "error", "error": str(e)}})

@app.post("/v1/tasks/ingest")
async def create_ingest_task(payload: IngestPayload):
    task_id = str(uuid.uuid4())
    get_db().tasks.update_one(
        {"task_id": task_id},
        {"$set": {
            "type": "ingest", "status": "queued",
            "user_id": payload.user_id,
            "created_at": time.time()}},
        upsert=True,
    )
    asyncio.create_task(_run_ingest_wrapper(task_id, payload))
    return {"task_id": task_id, "status": "queued"}

async def _run_ingest_wrapper(task_id: str, payload: IngestPayload):
    db = get_db()
    db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "running"}})
    try:
        await run_ingest_task(
            task_id,
            payload.user_id,
            payload.document_url,
            payload.document_id,
            payload.max_chars or 1500,
            payload.overlap or 150,
        )
        db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "done"}})
    except Exception as e:
        db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "error", "error": str(e)}})

@app.post("/v1/tasks/rag")
async def create_rag_task(payload: RagPayload):
    task_id = str(uuid.uuid4())
    get_db().tasks.update_one(
        {"task_id": task_id},
        {"$set": {
            "type": "rag", "status": "queued",
            "user_id": payload.user_id, "session_id": payload.session_id,
            "created_at": time.time()}},
        upsert=True,
    )
    asyncio.create_task(_run_rag_wrapper(task_id, payload))
    return {"task_id": task_id, "status": "queued"}

async def _run_rag_wrapper(task_id: str, payload: RagPayload):
    db = get_db()
    db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "running"}})
    try:
        await run_rag_task(task_id, payload.user_id, payload.session_id, payload.query, payload.related_document_id)
        db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "done"}})
    except Exception as e:
        db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "error", "error": str(e)}})


@app.post("/v1/tasks/recipes")
async def create_recipe_task(payload: RecipePayload):
    task_id = str(uuid.uuid4())
    prompt = (payload.dish or payload.query or "").strip()
    lang = (payload.lang or "tr").strip()

    get_db().tasks.update_one(
        {"task_id": task_id},
        {"$set": {
            "type": "recipes",
            "status": "queued",
            "user_id": payload.user_id,
            "session_id": payload.session_id,
            "prompt": prompt,
            "lang": lang,
            "created_at": time.time(),
        }},
        upsert=True,
    )
    asyncio.create_task(_run_recipe_wrapper(task_id, payload.user_id, payload.session_id, prompt, lang))
    return {"task_id": task_id, "status": "queued"}

async def _run_recipe_wrapper(task_id: str, user_id: str, session_id: str, prompt: str, lang: str):
    db = get_db()
    db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "running"}})
    try:
        await run_recipe_task(task_id, user_id, session_id, prompt, lang=lang)
        db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "done"}})
    except Exception as e:
        db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "error", "error": str(e)}})

@app.post("/v1/tasks/travel")
async def create_travel_task(payload: TravelPayload):
    task_id = str(uuid.uuid4())
    get_db().tasks.update_one(
        {"task_id": task_id},
        {"$set": {
            "type": "travel", "status": "queued",
            "user_id": payload.user_id, "session_id": payload.session_id,
            "created_at": time.time()}},
        upsert=True,
    )
    asyncio.create_task(_run_travel_wrapper(task_id, payload))
    return {"task_id": task_id, "status": "queued"}

async def _run_travel_wrapper(task_id: str, payload: TravelPayload):
    db = get_db()
    db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "running"}})
    try:
        async for tok in stream_travel_plan(payload.user_id, payload.session_id, payload.query, payload.lang):
            await publish_event_async({"task_id": task_id, "type": "token", "content": tok})
        db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "done"}})
        await publish_event_async({"task_id": task_id}, )
        await publish_event_async({"task_id": task_id, "type": "done"})
    except Exception as e:
        db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "error", "error": str(e)}})
        await publish_event_async({"task_id": task_id, "type": "error", "message": str(e)})

# -------------------- WebSocket (backfill + cross-worker safe) --------------------

@app.websocket("/v1/stream/{task_id}")
async def stream_ws(ws: WebSocket, task_id: str, from_seq: Optional[int] = Query(default=None)):
    await ws.accept()
    db = get_db()
    last_seq = int(from_seq) if from_seq is not None else 0

    # BACKFILL
    for ev in db.streams.find({"task_id": task_id, "seq": {"$gt": last_seq}}).sort("seq", 1):
        s = int(ev.get("seq", 0))
        if s > last_seq:
            last_seq = s
            await _ws_send_json(ws, ev)

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
                cursor = db.streams.find({"task_id": task_id, "seq": {"$gt": last_seq}}).sort("seq", 1)
                for ev in cursor:
                    s = int(ev.get("seq", 0))
                    if s > last_seq:
                        last_seq = s
                        await _ws_send_json(ws, ev)
                await asyncio.sleep(0.25)
        except Exception:
            pass

    bus_task = asyncio.create_task(pump_bus())
    db_task = asyncio.create_task(pump_db())

    try:
        await asyncio.gather(bus_task, db_task)
    except WebSocketDisconnect:
        pass
    finally:
        bus_task.cancel()
        db_task.cancel()
        await EVENT_BUS.unsubscribe(task_id, q)
