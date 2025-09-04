from pydantic import BaseModel
from typing import Optional

class TravelPayload(BaseModel):
    user_id: str
    session_id: str
    query: str
    lang: Optional[str] = None
