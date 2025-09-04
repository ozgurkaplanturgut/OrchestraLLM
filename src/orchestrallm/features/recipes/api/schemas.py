from pydantic import BaseModel
from typing import Optional

class RecipePayload(BaseModel):
    user_id: str
    session_id: str
    dish: Optional[str] = None
    query: Optional[str] = None
    lang: Optional[str] = None
