from __future__ import annotations
import time
from fastapi import APIRouter

router = APIRouter(tags=["health"])

@router.get("/health")
def health():
    return {"ok": True, "ts": time.time()}
