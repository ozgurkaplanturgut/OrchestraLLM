from __future__ import annotations

import asyncio
import io
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from pypdf import PdfReader
from qdrant_client import QdrantClient

from orchestrallm.shared.config.settings import settings
from orchestrallm.shared.eventbus.events import send_status, send_error, send_done
from orchestrallm.shared.llm.openai_client import embed_texts_sync
from orchestrallm.features.rag.infra.qdrant_util import ensure_collection, upsert_points
from orchestrallm.features.documents.domain.chunking import chunk_text

logger = logging.getLogger(__name__)

DOWNLOAD_TIMEOUT_S = 60
HEARTBEAT_EVERY_S = 15


def _is_pdf_url(u: str) -> bool:
    return urlparse(u).path.lower().endswith(".pdf")


async def _download_bytes(url: str, timeout: int = DOWNLOAD_TIMEOUT_S) -> bytes:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


def _bytes_to_text(b: bytes, pdf: bool) -> str:
    if pdf:
        reader = PdfReader(io.BytesIO(b))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    try:
        return b.decode("utf-8", errors="ignore")
    except Exception:
        return b.decode("latin-1", errors="ignore")


async def _heartbeat(task_id: str, label: str):
    while True:
        await asyncio.sleep(HEARTBEAT_EVERY_S)
        try:
            await send_status(task_id, f"[heartbeat] {label} running...")
        except Exception:
            return


async def run_ingest_task(
    task_id: str,
    user_id: str,
    document_url: str,
    document_id: Optional[str] = None,
    max_chars: int = 1500,
    overlap: int = 150,
):
    """
    Orchestrates the ingestion of a document:
      - Downloads it
      - Converts it to text
      - Splits into chunks
      - Generates embeddings
      - Stores vectors in Qdrant
    """
    if not settings.OPENAI_API_KEY:
        await send_error(task_id, "OPENAI_API_KEY is not defined.")
        return

    hb = asyncio.create_task(_heartbeat(task_id, "ingest"))
    try:
        await send_status(task_id, "Downloading...")
        raw = await _download_bytes(document_url)

        await send_status(task_id, "Converting to text...")
        text = _bytes_to_text(raw, _is_pdf_url(document_url))

        await send_status(task_id, "Splitting into chunks...")
        chunks = chunk_text(text, max_chars=max_chars, overlap=overlap)
        if not chunks:
            await send_error(task_id, "Empty content.")
            return

        await send_status(task_id, "Computing embeddings...")
        vectors = await asyncio.to_thread(embed_texts_sync, chunks)

        await send_status(task_id, "Writing to Qdrant...")
        qc = QdrantClient(url=settings.QDRANT_URL, api_key=getattr(settings, "QDRANT_API_KEY", None))
        ensure_collection(qc, settings.QDRANT_COLLECTION, settings.EMBEDDING_DIMENSIONS)

        doc_id = document_id or document_url
        payloads: List[Dict[str, Any]] = []
        for i, chunk in enumerate(chunks):
            payloads.append(
                {
                    "user_id": user_id,
                    "document_id": doc_id,
                    "chunk_index": i,
                    "text": chunk,
                    "source_url": document_url,
                    "created_at": time.time(),
                }
            )

        upsert_points(
            qc,
            collection_name=settings.QDRANT_COLLECTION,
            vectors=vectors,
            payloads=payloads,
            document_id=doc_id,
        )

        await send_status(task_id, f"Completed. {len(chunks)} chunks added.")
        await send_done(task_id)
    except Exception as e:
        await send_error(task_id, f"Error: {e}")
    finally:
        hb.cancel()
