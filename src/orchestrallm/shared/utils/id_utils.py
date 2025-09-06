from __future__ import annotations
import uuid

def make_point_uuid(document_id: str, chunk_index: int) -> str:
    """
    Generate a UUID for a document chunk based on document ID and chunk index.
    """
    key = f"{document_id}::{chunk_index}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))
