import os
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from groq import Groq
from dotenv import load_dotenv
from sqlalchemy.orm import Session

import database
from database import SessionLocal

load_dotenv()

app = FastAPI(title="AI Chatbot - Active Prototype")

groq_client = Groq()
GROQ_MODEL = os.getenv("GROQ_MODEL")

if not GROQ_MODEL:
    raise RuntimeError("CRITICAL CRASH: GROQ_MODEL environment variable is missing!")

# FastAPI Dependency Injection utility to manage safe connection lifetimes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class UserPayload(BaseModel):
    conversation_id: int
    session_id: int
    message: str
 
@app.get("/api/conversation/new")
async def start_new_chat_session(db: Session = Depends(get_db)):
    try:
        new_conv_id = database.create_new_conversation(db)
        return {"conversation_id": new_conv_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
async def process_chatbot_message(payload: UserPayload, db: Session = Depends(get_db)):
    try:
        database.update_conversation_title_if_new(db, payload.conversation_id, payload.message)

        database.save_message(db, payload.conversation_id, payload.session_id, "user", payload.message)
    
        db_history = database.get_chat_history(db, payload.conversation_id)
        
        formatted_messages = [
            {"role": "system", "content": "You are a concise, helpful backend chatbot assistant. You remember the conversation history provided below."}
        ]
        
        for msg in db_history:
            role = "user" if msg.sender_type == "user" else "assistant"
            formatted_messages.append({"role": role, "content": msg.content})
        
        # Submit the entire conversation thread bundle to Groq
        completion = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=formatted_messages,
            temperature=0.7
        )
        
        ai_response_text = completion.choices[0].message.content
    
        # Save the AI's response to the database before returning it to the user
        database.save_message(db, payload.conversation_id, payload.session_id, "bot", ai_response_text)
        
        return {
            "status": "success",
            "conversation_id": payload.conversation_id,
            "session_id": payload.session_id,
            "bot_reply": ai_response_text

        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))