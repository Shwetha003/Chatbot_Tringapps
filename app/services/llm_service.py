import os
from groq import Groq
from app.crud import chat as crud_chat

groq_client = Groq()
GROQ_MODEL = os.getenv("GROQ_MODEL")

if not GROQ_MODEL:
    raise RuntimeError("CRITICAL CRASH: GROQ_MODEL environment variable is missing!")

def generate_bot_reply(db, payload): 
    crud_chat.update_conversation_title_if_new(db, payload.conversation_id, payload.message)
    crud_chat.save_message(db, payload.conversation_id, payload.session_id, "user", payload.message)
    db_history = crud_chat.get_chat_history(db, payload.conversation_id)
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
    crud_chat.save_message(db, payload.conversation_id, payload.session_id, "bot", ai_response_text)

    return ai_response_text