# tasks/rag_tasks.py
"""
RAG task (history-aware) + terminal logging:
- (1) Konuşma geçmişini (user+session) yükle
- (2) Sorguyu embed et
- (3) Qdrant'tan top-k (user_id [+ document_id] filtresi) getir
- (4) Geçmiş + bağlam ile Chat Completions stream
- (5) Kullanıcı mesajını ve asistan cevabını geçmişe yaz
- (6) Tüm PROMPT (system + history + context), soru ve yanıtı terminale bas
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from utils.config import settings
from utils.events import send_token, send_error, send_done, send_status
from utils.history import load_history, append_message  # chat ile aynı API varsayımı
from utils.prompts import RAG_SYSTEM_PROMPT

from app.services.openai_client import stream_chat

# Runtime logger (uyarı/hata için)
_LOG_LEVEL = getattr(settings, "LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, _LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger("rag")


def _format_snippets(snippets: List[str]) -> str:
    if not snippets:
        return "(no retrieved snippets)"
    parts = []
    for i, s in enumerate(snippets, 1):
        parts.append(f"[Parça {i}]\n{s}")
    return "\n\n".join(parts)


# OpenAI helpers
async def _embed_query(text: str) -> List[float]:
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
        # 1) Konuşma geçmişini çek (son N mesaj)
        history_limit = getattr(settings, "HISTORY_MAX_TURNS", 10) or 10
        recent_msgs = load_history(user_id=user_id, session_id=session_id, limit=history_limit)

        # 2) Sorguyu embed et
        await send_status(task_id, "Sorgu embed ediliyor...")
        q_vec = await _embed_query(query)

        # 3) Qdrant araması (user_id [+ document_id] filtresi)
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

        # 4) Mesajları oluştur (SYSTEM + HISTORY + USER)
        context_text = _format_snippets(snippets)
        system_prompt = RAG_SYSTEM_PROMPT + "\n" + f"CONTEXT TEXT: {context_text}"

        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        # Konuşma geçmişini orijinal rolleriyle ekle
        for m in recent_msgs or []:
            role = m.get("role")
            content = m.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        # Şimdiki kullanıcı mesajı
        messages.append({"role": "user", "content": query})        

        # 5) Önce kullanıcı mesajını geçmişe yaz (süreklilik için)
        try:
            append_message(user_id=user_id, session_id=session_id, role="user", content=query)
        except Exception as e:
            logger.warning(f"history append (user) failed: {e}")

        # 6) Stream cevap + cevabı biriktir
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

        # 7) Asistan cevabını da geçmişe yaz
        try:
            append_message(user_id=user_id, session_id=session_id, role="assistant", content=final_text)
        except Exception as e:
            logger.warning(f"history append (assistant) failed: {e}")

        # ---- TERMINAL LOG: RESPONSE (kapanış) ----
        try:
            print("# RESPONSE:")
            print(final_text)
            print("======= RAG END =======\n")
        except Exception as e:
            logger.warning(f"terminal response log failed: {e}")

        await send_done(task_id)

    except Exception as e:
        logger.exception("RAG task error")
        await send_error(task_id, f"RAG task hata: {e}")
