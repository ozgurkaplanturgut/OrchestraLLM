from __future__ import annotations

from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from orchestrallm.shared.utils.id_utils import make_point_uuid

def ensure_collection(client: QdrantClient, name: str, vector_size: int) -> None:
    try:
        client.get_collection(name)
    except Exception:
        client.recreate_collection(
            collection_name=name,
            vectors_config=qm.VectorParams(size=vector_size, distance=qm.Distance.COSINE),
        )

def build_filter(*, user_id: Optional[str] = None, related_document_id: Optional[str] = None) -> Optional[qm.Filter]:
    must: List[qm.FieldCondition] = []
    if user_id:
        must.append(qm.FieldCondition(key="user_id", match=qm.MatchValue(value=user_id)))
    if related_document_id:
        must.append(qm.FieldCondition(key="document_id", match=qm.MatchValue(value=related_document_id)))
    return qm.Filter(must=must) if must else None

def upsert_points(
    client: QdrantClient,
    *,
    collection_name: str,
    vectors: List[List[float]],
    payloads: List[Dict[str, Any]],
    document_id: str,
) -> List[str]:
    assert len(vectors) == len(payloads), "vectors/payloads length mismatch"
    points: List[qm.PointStruct] = []
    for idx, (vec, pl) in enumerate(zip(vectors, payloads)):
        pid = make_point_uuid(document_id, idx)
        points.append(qm.PointStruct(id=pid, vector=vec, payload=pl))
    client.upsert(collection_name=collection_name, points=points)
    return [str(p.id) for p in points]

def search(
    client: QdrantClient,
    *,
    collection_name: str,
    query_vector: List[float],
    limit: int = 5,
    query_filter: Optional[qm.Filter] = None,
    with_payload: bool = True,
    with_vectors: bool = False,
):
    return client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        query_filter=query_filter,
        limit=limit,
        with_payload=with_payload,
        with_vectors=with_vectors,
    )
