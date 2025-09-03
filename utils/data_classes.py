from pydantic import BaseModel
from typing import Optional

class ChatPayload(BaseModel):
    user_id: str
    session_id: str
    query: str

class IngestPayload(BaseModel):
    user_id: str
    document_url: str
    document_id: Optional[str] = None
    max_chars: Optional[int] = 1500
    overlap: Optional[int] = 150

class RagPayload(BaseModel):
    user_id: str
    session_id: str
    query: str
    related_document_id: Optional[str] = None

class TravelPayload(BaseModel):
    user_id: str
    session_id: str
    query: str
    lang: Optional[str] = None

class RecipePayload(BaseModel):
    user_id: str
    session_id: str
    dish: Optional[str] = None
    query: Optional[str] = None
    lang: Optional[str] = None