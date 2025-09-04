from pydantic import BaseModel

class ChatPayload(BaseModel):
    user_id: str
    session_id: str
    query: str
