from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Index
from datetime import datetime
from app.core.database import Base

class ChatConversation(Base):
    __tablename__ = "chat_conversations"  

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), default="New Conversation")
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="active")

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    message_id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(Integer, default=1)
    sender_type = Column(String(10), nullable=False) 
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

Index('idx_messages_conversation_id', ChatMessage.conversation_id)
