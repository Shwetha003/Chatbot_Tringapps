import os
from groq import AsyncGroq
from app.crud import chat as crud_chat
from app.schemas.chat import UserPayload

groq_client = AsyncGroq()
GROQ_MODEL = os.getenv("GROQ_MODEL")

if not GROQ_MODEL:
    raise RuntimeError("CRITICAL CRASH: GROQ_MODEL environment variable is missing!")

async def generate_bot_reply(db, payload: UserPayload, context: str = ""): 
    crud_chat.update_conversation_title_if_new(db, payload.conversation_id, payload.message)
    crud_chat.save_message(db, payload.conversation_id, payload.session_id, "user", payload.message)

    db_history = crud_chat.get_chat_history(db, payload.conversation_id)

    system_content = "You are a concise, helpful chatbot assistant. You remember the conversation history provided below."
    
    if context:
        system_content += (
            "\n\nContext from uploaded document:\n"
            "Use the parsed layout details below to accurately handle the user's prompt. "
            "It includes raw text, reconstructed structural layout data tables, and vision-model explanations of diagrams.\n"
            f"--- START DOCUMENT ---\n{context}\n--- END DOCUMENT ---"
        )

    formatted_messages = [{"role": "system", "content": system_content}]
    
    for msg in db_history:
        role = "user" if msg.sender_type == "user" else "assistant"
        formatted_messages.append({"role": role, "content": msg.content})
    
    # Submit the entire conversation thread bundle to Groq
    completion = await groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=formatted_messages,
        temperature=0.7
    )

    ai_response_text = completion.choices[0].message.content
    crud_chat.save_message(db, payload.conversation_id, payload.session_id, "bot", ai_response_text)

    return ai_response_text