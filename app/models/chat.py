from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None

# ==========================================
# TABLE 1: Documents Table
# ==========================================
class Document(Base):
    __tablename__ = "documents"

    document_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    document_name = Column(String(255), nullable=False)
    source_url = Column(Text, nullable=True)  
    file_type = Column(String(50), nullable=False)  
    chunk_count = Column(Integer, default=0)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Relationships
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


# ==========================================
# TABLE 2: Chunks Table
# ==========================================
class Chunk(Base):
    __tablename__ = "chunks"

    chunk_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    doc_id = Column(Integer, ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False)
    chunk_content = Column(Text, nullable=False)
    
    # 1536 dimensions for embeddings
    embedding = Column(Vector(1536) if Vector else Text, nullable=True) 

    # Relationships
    document = relationship("Document", back_populates="chunks")


# ==========================================
# TABLE 3: Conversation Table
# ==========================================
class ChatConversation(Base):
    __tablename__ = "chat_conversations"  

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), default="New Conversation")
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="active")
    
    extracted_markdown = Column(Text, nullable=True)
    extracted_json = Column(Text, nullable=True)

    # Relationships
    messages = relationship("ChatMessage", back_populates="conversation", cascade="all, delete-orphan")


# ==========================================
# TABLE 4: Chat Messages Table 
# ==========================================
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    message_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(Integer, default=1, nullable=False)
    sender_type = Column(String(10), nullable=False)  # 'user' or 'bot'
    content = Column(Text, nullable=False)            # Stores the actual message text
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    conversation = relationship("ChatConversation", back_populates="messages")


# Database Optimization Indexes
Index('idx_chunks_doc_id', Chunk.doc_id)
Index('idx_messages_convo_session', ChatMessage.conversation_id, ChatMessage.session_id)