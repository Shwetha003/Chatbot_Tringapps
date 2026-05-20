import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from groq import Groq
from dotenv import load_dotenv

# 1. Inject configurations from the local environment file
load_dotenv()

# 2. Fire up the FastAPI engine
app = FastAPI(title="AI Chatbot - Active Prototype")

# 3. Instantiate the Groq engine securely
if not os.getenv("GROQ_API_KEY"):
    raise RuntimeError("CRITICAL CRASH: The GROQ_API_KEY variable is missing!")

GROQ_MODEL = os.getenv("GROQ_MODEL")
if not GROQ_MODEL:
    raise RuntimeError("CRITICAL CRASH: The GROQ_MODEL variable is missing from the configuration!")

groq_client = Groq()

# 4. Construct the structural data contract for incoming data
class UserPayload(BaseModel):
    message: str

# 5. Define the web accessible POST path
@app.post("/api/chat")
async def process_chatbot_message(payload: UserPayload):
    try:
        # Submit the user's message directly to Groq's LPU system
        # Using llama-3.3-70b-versatile for high-quality production reasoning
        completion = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You are a concise, helpful backend chatbot agent."},
                {"role": "user", "content": payload.message}
            ],
            temperature=0.7
        )
        
        # Pull the text reply from Groq's nested JSON response wrapper
        ai_response_text = completion.choices[0].message.content
    
        
        return {
            "status": "success",
            "bot_reply": ai_response_text

        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Groq Infrastructure Error: {str(e)}")