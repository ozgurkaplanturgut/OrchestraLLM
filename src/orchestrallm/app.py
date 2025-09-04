from __future__ import annotations

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from orchestrallm.shared.config.settings import settings
from orchestrallm.shared.logging.logger import setup_logging
from orchestrallm.shared.persistence.mongo import ensure_indexes

from orchestrallm.shared.api.health import router as health_router
from orchestrallm.shared.eventbus.api import router as stream_router
from orchestrallm.features.chat.api.routes import router as chat_router
from orchestrallm.features.documents.api.routes import router as documents_router
from orchestrallm.features.rag.api.routes import router as rag_router
from orchestrallm.features.recipes.api.routes import router as recipes_router
from orchestrallm.features.travel.api.routes import router as travel_router

log = logging.getLogger("app")

def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="OrchestraLLM", version="1.0.0")

    # CORS
    allow_origins = (
        [o.strip() for o in (settings.CORS_ALLOW_ORIGINS or "").split(",")]
        if getattr(settings, "CORS_ALLOW_ORIGINS", None) and settings.CORS_ALLOW_ORIGINS != "*"
        else ["*"]
    )
    allow_methods = (
        [m.strip() for m in (settings.CORS_ALLOW_METHODS or "").split(",")]
        if getattr(settings, "CORS_ALLOW_METHODS", None) and settings.CORS_ALLOW_METHODS != "*"
        else ["*"]
    )
    allow_headers = (
        [h.strip() for h in (settings.CORS_ALLOW_HEADERS or "").split(",")]
        if getattr(settings, "CORS_ALLOW_HEADERS", None) and settings.CORS_ALLOW_HEADERS != "*"
        else ["*"]
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=getattr(settings, "CORS_ALLOW_CREDENTIALS", True),
        allow_methods=allow_methods,
        allow_headers=allow_headers,
    )

    # Routers
    app.include_router(health_router)
    app.include_router(chat_router,      prefix="/v1")
    app.include_router(documents_router, prefix="/v1")
    app.include_router(rag_router,       prefix="/v1")
    app.include_router(recipes_router,   prefix="/v1")
    app.include_router(travel_router,    prefix="/v1")
    app.include_router(stream_router,    prefix="/v1")

    @app.on_event("startup")
    async def _on_startup():
        try:
            ensure_indexes()
        except Exception:
            log.warning("ensure_indexes failed or is a no-op")

    return app

# Uvicorn/Gunicorn entry point
app = create_app()
