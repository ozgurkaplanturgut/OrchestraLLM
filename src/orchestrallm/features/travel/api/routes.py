from __future__ import annotations
import asyncio, time, uuid
from fastapi import APIRouter
from orchestrallm.shared.persistence.mongo import get_db
from orchestrallm.shared.eventbus.events import publish_event_async
from .schemas import TravelPayload
from orchestrallm.features.travel.app.use_cases import run_travel_task

router = APIRouter(tags=["tasks:travel"])

@router.post("/tasks/travel")
async def create_travel_task(payload: TravelPayload):
    task_id = str(uuid.uuid4())
    get_db().tasks.update_one(
        {"task_id": task_id},
        {"$set": {"type":"travel","status":"queued","user_id":payload.user_id,"session_id":payload.session_id,"created_at":time.time()}},
        upsert=True,
    )
    asyncio.create_task(_run(task_id, payload))
    return {"task_id": task_id, "status": "queued"}

async def _run(task_id: str, payload: TravelPayload):
    db = get_db()
    db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "running"}})
    try:
        await run_travel_task(task_id, payload.user_id, payload.session_id, payload.query)
        db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "done"}})
        await publish_event_async({"task_id": task_id, "type": "done"})
    except Exception as e:
        db.tasks.update_one({"task_id": task_id}, {"$set": {"status": "error","error": str(e)}})
        await publish_event_async({"task_id": task_id, "type": "error", "message": str(e)})
