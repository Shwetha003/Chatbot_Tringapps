from pydantic import BaseModel

class UserPayload(BaseModel):
    conversation_id: int
    session_id: int
    message: str
