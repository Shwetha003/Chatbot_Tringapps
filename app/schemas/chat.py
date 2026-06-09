from pydantic import BaseModel
from fastapi import Form
from typing import Optional

class UserPayload(BaseModel):
    conversation_id: int
    session_id: int
    message: Optional[str] = None

    # lets FastAPI map form fields directly into this class
    @classmethod
    def as_form(
        cls,
        conversation_id: int = Form(...),
        session_id: str = Form(...),
        message: Optional[str] = Form(None)
    ):
        return cls(
            conversation_id=conversation_id,
            session_id=session_id,
            message=message
        )
