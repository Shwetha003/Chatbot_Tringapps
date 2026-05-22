import os
# import psycopg2
# from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

load_dotenv()

# 1. Database Connection URL string
DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

# 2. Establish the SQLAlchemy Communication Engine
engine = create_engine(DATABASE_URL)

# 3. Create a Local Session Factory (Our tool to execute DB transactions)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 4. Define the declarative base class that maps our Python classes to SQL tables
Base = declarative_base()

# DATA SCHEMAS / MODELS 

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

# Ensure our performance index is applied explicitly via the ORM metadata
Index('idx_messages_conversation_id', ChatMessage.conversation_id)


# DATABASE OPERATION FUNCTIONS

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



# # Function to establish a fresh connection to PostgreSQL
# def get_db_connection():
#     try:
#         connection = psycopg2.connect(
#             host=os.getenv("DB_HOST"),
#             database=os.getenv("DB_NAME"),
#             user=os.getenv("DB_USER"),
#             password=os.getenv("DB_PASSWORD"),
#             port=os.getenv("DB_PORT")
#         )
#         return connection
#     except Exception as e:
#         print(f"DATABASE CONNECTION ERROR: {str(e)}")

# def create_new_session():
#     conn = get_db_connection()
#     cursor = conn.cursor()
#     cursor.execute("INSERT INTO chat_conversations DEFAULT VALUES RETURNING id;")
#     conversation_id = cursor.fetchone()[0]
#     conn.commit()
#     cursor.close()
#     conn.close()
#     return conversation_id

# def update_conversation_title_if_new(conversation_id: int, first_message: str):
#     conn = get_db_connection()
#     cursor = conn.cursor()
    
#     # Check if the title is still the default fallback
#     cursor.execute("SELECT title FROM chat_conversations WHERE id = %s;", (conversation_id,))
#     current_title = cursor.fetchone()[0]
    
#     if current_title == 'New Conversation':
#         # Clean up the message text to act as a title (clip it to 50 characters max)
#         truncated_title = first_message[:50] + "..." if len(first_message) > 50 else first_message
        
#         cursor.execute(
#             "UPDATE chat_conversations SET title = %s WHERE id = %s;",
#             (truncated_title, conversation_id)
#         )
#         conn.commit()
        
#     cursor.close()
#     conn.close()

# def save_message(conversation_id: int,session_id: int, sender_type: str, content: str):
#     conn = get_db_connection()
#     cursor = conn.cursor()
    
#     cursor.execute(
#         """
#         INSERT INTO chat_messages (conversation_id, session_id, sender_type, content)
#         VALUES (%s, %s, %s, %s);
#         """,
#         (conversation_id, session_id, sender_type, content)
#     )
    
#     conn.commit()
#     cursor.close()
#     conn.close()

# # 3. Function to pull the past N messages of a specific session to give to the AI
# def get_chat_history(conversation_id: int, limit: int = 12):
#     conn = get_db_connection()
#     cursor = conn.cursor(cursor_factory=RealDictCursor)
    
#     cursor.execute(
#         """
#         SELECT sender_type, content 
#         FROM chat_messages 
#         WHERE conversation_id = %s 
#         ORDER BY created_at ASC 
#         LIMIT %s;
#         """,
#         (conversation_id, limit)
#     )
    
#     history = cursor.fetchall()
#     cursor.close()
#     conn.close()
#     return history  