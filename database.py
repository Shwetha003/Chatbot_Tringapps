import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

# Function to establish a fresh connection to PostgreSQL
def get_db_connection():
    try:
        connection = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            port=os.getenv("DB_PORT")
        )
        return connection
    except Exception as e:
        print(f"DATABASE CONNECTION ERROR: {str(e)}")

def create_new_session():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_conversations DEFAULT VALUES RETURNING id;")
    conversation_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    return conversation_id

def update_conversation_title_if_new(conversation_id: int, first_message: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if the title is still the default fallback
    cursor.execute("SELECT title FROM chat_conversations WHERE id = %s;", (conversation_id,))
    current_title = cursor.fetchone()[0]
    
    if current_title == 'New Conversation':
        # Clean up the message text to act as a title (clip it to 50 characters max)
        truncated_title = first_message[:50] + "..." if len(first_message) > 50 else first_message
        
        cursor.execute(
            "UPDATE chat_conversations SET title = %s WHERE id = %s;",
            (truncated_title, conversation_id)
        )
        conn.commit()
        
    cursor.close()
    conn.close()

def save_message(conversation_id: int,session_id: int, sender_type: str, content: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        INSERT INTO chat_messages (conversation_id, session_id, sender_type, content)
        VALUES (%s, %s, %s, %s);
        """,
        (conversation_id, session_id, sender_type, content)
    )
    
    conn.commit()
    cursor.close()
    conn.close()

# 3. Function to pull the past N messages of a specific session to give to the AI
def get_chat_history(conversation_id: int, limit: int = 12):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute(
        """
        SELECT sender_type, content 
        FROM chat_messages 
        WHERE conversation_id = %s 
        ORDER BY created_at ASC 
        LIMIT %s;
        """,
        (conversation_id, limit)
    )
    
    history = cursor.fetchall()
    cursor.close()
    conn.close()
    return history  