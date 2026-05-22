import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from groq import Groq
from dotenv import load_dotenv

import database

load_dotenv()

app = FastAPI(title="AI Chatbot - Active Prototype")

if not os.getenv("GROQ_API_KEY"):
    raise RuntimeError("CRITICAL CRASH: The GROQ_API_KEY variable is missing!")

GROQ_MODEL = os.getenv("GROQ_MODEL")
if not GROQ_MODEL:
    raise RuntimeError("CRITICAL CRASH: The GROQ_MODEL variable is missing from the configuration!")

groq_client = Groq()

class UserPayload(BaseModel):
    conversation_id: int
    session_id: int
    message: str

@app.get("/api/conversation/new")
async def start_new_chat_session():
    try:
        new_conv_id = database.create_new_session()
        return {"conversation_id": new_conv_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
async def process_chatbot_message(payload: UserPayload):
    try:
        database.update_conversation_title_if_new(payload.conversation_id, payload.message)

        database.save_message(payload.conversation_id, payload.session_id, "user", payload.message)
    
        db_history = database.get_chat_history(payload.conversation_id)
        
        formatted_messages = [
            {"role": "system", "content": "You are a concise, helpful backend chatbot assistant. You remember the conversation history provided below."}
        ]
        
        for msg in db_history:
            role = "user" if msg['sender_type'] == "user" else "assistant"
            formatted_messages.append({"role": role, "content": msg['content']})
        
        # Submit the entire conversation thread bundle to Groq
        completion = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=formatted_messages,
            temperature=0.7
        )
        
        # Pull the text reply from Groq's nested JSON response wrapper
        ai_response_text = completion.choices[0].message.content
    
        # Save the AI's response to the database before returning it to the user
        database.save_message(payload.conversation_id, payload.session_id, "bot", ai_response_text)
        
        return {
            "status": "success",
            "conversation_id": payload.conversation_id,
            "session_id": payload.session_id,
            "bot_reply": ai_response_text

        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))