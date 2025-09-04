from pydantic import BaseModel
from typing import Optional

class RagPayload(BaseModel):
    user_id: str
    session_id: str
    query: str
    related_document_id: Optional[str] = None
