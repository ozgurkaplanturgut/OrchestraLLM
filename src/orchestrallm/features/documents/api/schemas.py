from pydantic import BaseModel
from typing import Optional

class IngestPayload(BaseModel):
    user_id: str
    document_url: str
    document_id: Optional[str] = None
    max_chars: Optional[int] = 1500
    overlap: Optional[int] = 150
