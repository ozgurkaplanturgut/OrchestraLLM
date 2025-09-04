# app/rag/rag_core.py
"""
This module provides core functionalities for Retrieval-Augmented Generation (RAG) using Qdrant as the vector database.
"""

from typing import List, Dict, Any, Optional

from qdrant_client import QdrantClient
from orchestrallm.shared.config.settings import settings
from orchestrallm.features.rag.infra.qdrant_util import ensure_collection, search
from orchestrallm.shared.llm.openai_client import embed_query_sync


def retrieve_passages(
    user_id: str,
    query: str,
    related_document_id: Optional[str] = None,
    top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    This function retrieves relevant passages from the Qdrant vector database based on the input query.
    """
    v = embed_query_sync(query)
    if not v:
        return []

    client = QdrantClient(url=settings.QDRANT_URL)
    ensure_collection(client, settings.QDRANT_COLLECTION, vector_size=len(v), distance="Cosine")

    hits = search(
        client=client,
        collection_name=settings.QDRANT_COLLECTION,
        query_vector=v,
        top_k=top_k or settings.RAG_TOP_K,
        user_id=user_id,
        related_document_id=related_document_id,
        with_payload=True,
    )

    passages: List[Dict[str, Any]] = []
    for h in hits:
        pl = (h.payload or {})
        passages.append({
            "text": pl.get("text", ""),
            "score": getattr(h, "score", None),
            "document_id": pl.get("document_id"),
            "chunk_index": pl.get("chunk_index"),
        })
    return passages


def build_context(passages: List[Dict[str, Any]], max_chars: int = 4000) -> str:
    """
    This function builds a context string by concatenating passage texts up to a maximum character limit.
    """
    buf: List[str] = []
    total = 0
    for p in passages:
        t = p.get("text") or ""
        if not t:
            continue
        if total + len(t) > max_chars:
            break
        buf.append(t)
        total += len(t)
    return "\n\n".join(buf)
