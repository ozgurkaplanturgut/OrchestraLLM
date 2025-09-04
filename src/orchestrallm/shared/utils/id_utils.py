# utils/id_utils.py
from __future__ import annotations
import uuid

def make_point_uuid(document_id: str, chunk_index: int) -> str:
    """
    Aynı (document_id, chunk_index) => aynı UUID5 (deterministik).
    """
    key = f"{document_id}::{chunk_index}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))
