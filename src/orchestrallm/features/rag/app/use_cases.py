# tasks/rag_tasks.py
"""
This module defines a task for handling Retrieval-Augmented Generation (RAG) using Qdrant and OpenAI.
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from orchestrallm.shared.config.settings import settings
from orchestrallm.shared.eventbus.events import send_token, send_error, send_done, send_status
from orchestrallm.shared.history import load_history, append_message  # chat ile aynı API varsayımı
from orchestrallm.features.rag.domain.prompts import RAG_SYSTEM_PROMPT

from orchestrallm.shared.llm.openai_client import stream_chat

# Runtime logger (uyarı/hata için)
_LOG_LEVEL = getattr(settings, "LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, _LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger("rag")


def _format_snippets(snippets: List[str]) -> str:
    """
    Format retrieved snippets into a single context text.
    """
    if not snippets:
        return "(no retrieved snippets)"
    parts = []
    for i, s in enumerate(snippets, 1):
        parts.append(f"[Parça {i}]\n{s}")
    return "\n\n".join(parts)


# OpenAI helpers
async def _embed_query(text: str) -> List[float]:
    """
    Embed the query text using OpenAI embeddings API.
    """
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"model": settings.EMBEDDING_MODEL, "input": text}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{settings.OPENAI_BASE_URL}/embeddings", headers=headers, json=payload)
        r.raise_for_status()
        j = r.json()
        return j["data"][0]["embedding"]


# Qdrant helpers
def _qdrant() -> QdrantClient:
    """
    Create and return a Qdrant client.
    """
    # grpc kapalı; httpx client kullanımı ile uyumlu
    return QdrantClient(url=settings.QDRANT_URL, prefer_grpc=False)


def _build_filter(user_id: str, related_document_id: Optional[str]) -> Filter:
    must = [FieldCondition(key="user_id", match=MatchValue(value=user_id))]
    if related_document_id:
        must.append(FieldCondition(key="document_id", match=MatchValue(value=related_document_id)))
    return Filter(must=must)


# Main task
async def run_rag_task(
    task_id: str,
    user_id: str,
    session_id: str,
    query: str,
    related_document_id: Optional[str],
    mode: str = "multi",
):
    """
    This function handles a RAG (Retrieval-Augmented Generation) task by managing the conversation history,
    retrieving relevant documents from Qdrant, and interacting with the OpenAI API. It streams the response
    back to the client in real-time.
    """
    if not settings.OPENAI_API_KEY:
        await send_error(task_id, "OPENAI_API_KEY tanımlı değil.")
        return

    try:
        history_limit = getattr(settings, "HISTORY_MAX_TURNS", 10) or 10
        recent_msgs = load_history(user_id=user_id, session_id=session_id, limit=history_limit)

        await send_status(task_id, "Sorgu embed ediliyor...")
        q_vec = await _embed_query(query)

        await send_status(task_id, "Qdrant araması yapılıyor...")
        client = _qdrant()
        res = client.search(
            collection_name=settings.QDRANT_COLLECTION,
            query_vector=q_vec,
            limit=getattr(settings, "RAG_TOPK", 5) or 5,
            query_filter=_build_filter(user_id=user_id, related_document_id=related_document_id),
            with_payload=True,
            with_vectors=False,
        )
        snippets = [hit.payload.get("text", "") for hit in res]

        context_text = _format_snippets(snippets)
        system_prompt = RAG_SYSTEM_PROMPT + "\n" + f"CONTEXT TEXT: {context_text}"

        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for m in recent_msgs or []:
            role = m.get("role")
            content = m.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": query})        

        try:
            append_message(user_id=user_id, session_id=session_id, role="user", content=query)
        except Exception as e:
            logger.warning(f"history append (user) failed: {e}")

        final_chunks: List[str] = []
        try:
            async for tok in stream_chat(messages):
                final_chunks.append(tok)
                await send_token(task_id, tok)
        except httpx.HTTPError as e:
            await send_error(task_id, f"OpenAI HTTP hatası: {e}")
            return
        except Exception as e:
            await send_error(task_id, f"Hata: {e}")
            return

        final_text = "".join(final_chunks).strip()

        try:
            append_message(user_id=user_id, session_id=session_id, role="assistant", content=final_text)
        except Exception as e:
            logger.warning(f"history append (assistant) failed: {e}")

        await send_done(task_id)

    except Exception as e:
        logger.exception("RAG task error")
        await send_error(task_id, f"RAG task hata: {e}")
