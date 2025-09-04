from __future__ import annotations
import asyncio, time, uuid
from fastapi import APIRouter
from orchestrallm.shared.persistence.mongo import get_db
from orchestrallm.shared.eventbus.events import publish_event_async
from .schemas import IngestPayload
from orchestrallm.features.documents.app.use_cases import run_ingest_task

router = APIRouter(tags=["tasks:ingest"])

@router.post("/tasks/ingest")
async def create_ingest_task(payload: IngestPayload):
    task_id = str(uuid.uuid4())
    get_db().tasks.update_one(
        {"task_id": task_id},
        {"$set": {"type":"ingest","status":"queued","user_id":payload.user_id,"created_at":time.time()}},
        upsert=True,
    )
    asyncio.create_task(_run(task_id, payload))
    return {"task_id": task_id, "status": "queued"}

async def _run(task_id: str, payload: IngestPayload):
    db = get_db()
    db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "running"}})
    try:
        await run_ingest_task(task_id, payload.user_id, payload.document_url, payload.document_id, payload.max_chars or 1500, payload.overlap or 150)
        db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "done"}})
        await publish_event_async({"task_id": task_id, "type": "done"})
    except Exception as e:
        db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "error","error": str(e)}})
        await publish_event_async({"task_id": task_id, "type": "error", "message": str(e)})
