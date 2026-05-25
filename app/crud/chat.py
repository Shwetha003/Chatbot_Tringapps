from sqlalchemy.orm import Session
from app.models.chat import ChatConversation, ChatMessage

def create_new_conversation(db):
    new_conv = ChatConversation()
    db.add(new_conv)
    db.commit()
    db.refresh(new_conv)  # Refreshes the object to grab its new auto-generated ID
    return new_conv.id

def update_conversation_title_if_new(db, conversation_id: int, first_message: str):
    conv = db.query(ChatConversation).filter(ChatConversation.id == conversation_id).first()
    
    if conv and conv.title == "New Conversation":
        truncated_title = first_message[:50] + "..." if len(first_message) > 50 else first_message
        conv.title = truncated_title
        db.commit()

def save_message(db, conversation_id: int, session_id: int, sender_type: str, content: str):
    new_msg = ChatMessage(
        conversation_id=conversation_id,
        session_id=session_id,
        sender_type=sender_type,
        content=content
    )
    db.add(new_msg)
    db.commit()

def get_chat_history(db, conversation_id: int, limit: int = 12):
    return db.query(ChatMessage)\
             .filter(ChatMessage.conversation_id == conversation_id)\
             .order_by(ChatMessage.created_at.asc())\
             .limit(limit)\
             .all()
