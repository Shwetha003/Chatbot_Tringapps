from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.chat import UserPayload
from app.crud import chat as crud_chat
from app.services import llm_service

router = APIRouter(prefix="/api")

@router.get("/api/conversation/new")
async def start_new_chat_session(db: Session = Depends(get_db)):
    try:
        new_conv_id = crud_chat.create_new_conversation(db)
        return {"conversation_id": new_conv_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/chat")
async def process_chatbot_message(payload: UserPayload, db: Session = Depends(get_db)):
    try:
        bot_reply=llm_service.generate_bot_reply(db,payload)
        return {
            "status": "success",
            "conversation_id": payload.conversation_id,
            "session_id": payload.session_id,
            "bot_reply": bot_reply

        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
