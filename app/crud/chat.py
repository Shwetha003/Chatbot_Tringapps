from sqlalchemy.orm import Session
from app.models.chat import Document, Chunk, ChatConversation, ChatMessage
import json

# 1. Create Conversation
def create_new_conversation(db: Session) -> int:
    new_conv = ChatConversation(title="New Conversation", status="active")
    db.add(new_conv)
    db.commit()
    db.refresh(new_conv)
    return new_conv.id

# 2. Save Markdown/JSON Context strings
def save_parsed_document_data(db: Session, conversation_id: int, markdown_text: str, json_dict: dict):
    
    conv = db.query(ChatConversation).filter(ChatConversation.id == conversation_id).first()
    if conv:
        conv.extracted_markdown = markdown_text
        conv.extracted_json = json.dumps(json_dict) if isinstance(json_dict, dict) else json_dict
        db.commit()
    return conv

# 3. Save Document Tracker Meta info
def create_document_record(db: Session, document_name: str, file_type: str, source_url: str = None, chunk_count: int = 0):
    new_doc = Document(
        document_name=document_name,
        file_type=file_type,
        source_url=source_url,
        chunk_count=chunk_count
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)
    return new_doc

# 4. Save Chat History Messaging rows
def save_message(db: Session, conversation_id: int, session_id: int, sender_type: str, content: str):
    new_msg = ChatMessage(
        conversation_id=conversation_id,
        session_id=session_id,
        sender_type=sender_type,
        content=content
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)
    return new_msg

def update_conversation_title_if_new(db: Session, conversation_id: int, first_message: str):
    """
    Updates the conversation title using a snippet of the first user message 
    if it's still set to the default title.
    """
    conv = db.query(ChatConversation).filter(ChatConversation.id == conversation_id).first()
    if conv and conv.title == "New Conversation":
        # Snip the first 40 characters of the user message as a title placeholder
        snip = first_message[:40] + "..." if len(first_message) > 40 else first_message
        conv.title = snip
        db.commit()
    return conv

def get_chat_history(db: Session, conversation_id: int):
    """
    Retrieves all past messages belonging to a specific conversation,
    ordered chronologically so the LLM gets the proper thread history.
    """
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )