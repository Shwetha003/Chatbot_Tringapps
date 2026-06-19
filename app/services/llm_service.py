import os
from groq import AsyncGroq
from app.crud import chat as crud_chat
from app.schemas.chat import UserPayload

groq_client = AsyncGroq()
GROQ_MODEL = os.getenv("GROQ_MODEL")

if not GROQ_MODEL:
    raise RuntimeError("CRITICAL CRASH: GROQ_MODEL environment variable is missing!")


async def generate_bot_reply(db, payload: UserPayload, context: str = ""):

    print("\n========== REQUEST ==========")
    print("Conversation ID:", payload.conversation_id)
    print("Session ID:", payload.session_id)
    print("User Message:", payload.message)
    print("=============================\n")

    crud_chat.update_conversation_title_if_new(
        db,
        payload.conversation_id,
        payload.message
    )

    crud_chat.save_message(
        db,
        payload.conversation_id,
        payload.session_id,
        "user",
        payload.message
    )

    db_history = crud_chat.get_chat_history(
        db,
        payload.conversation_id
    )

    print("\n========== HISTORY ==========")
    print("History count:", len(db_history))

    for i, msg in enumerate(db_history):
        print(
            f"Message {i} | "
            f"Conv={msg.conversation_id} | "
            f"Role={msg.sender_type} | "
            f"Chars={len(msg.content)}"
        )

    print("=============================\n")

    system_content = (
        "You are a concise, helpful chatbot assistant. "
        "You remember the conversation history provided below."
    )

    if context:
        system_content += (
            "\n\nContext from uploaded document:\n"
            "Use the parsed layout details below to accurately handle the user's prompt. "
            "It includes raw text, reconstructed structural layout data tables, "
            "and vision-model explanations of diagrams.\n"
            f"--- START DOCUMENT ---\n{context}\n--- END DOCUMENT ---"
        )

    formatted_messages = [
        {
            "role": "system",
            "content": system_content
        }
    ]

    for msg in db_history:
        role = "user" if msg.sender_type == "user" else "assistant"

        formatted_messages.append(
            {
                "role": role,
                "content": msg.content
            }
        )

    print("\n========== DEBUG INFO ==========")

    print("Model:", GROQ_MODEL)

    print(
        "Context length:",
        len(context) if context else 0
    )

    print(
        "System content length:",
        len(system_content)
    )

    print(
        "History message count:",
        len(db_history)
    )

    total_chars = sum(
        len(str(msg["content"]))
        for msg in formatted_messages
    )

    print(
        "Total chars sent to Groq:",
        total_chars
    )

    print("================================\n")

    completion = await groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=formatted_messages,
        temperature=0.7
    )

    ai_response_text = completion.choices[0].message.content

    crud_chat.save_message(
        db,
        payload.conversation_id,
        payload.session_id,
        "bot",
        ai_response_text
    )

    return ai_response_text