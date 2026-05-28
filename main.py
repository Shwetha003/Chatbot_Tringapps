from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api.controllers import chat
from app.core.database import engine
from app.models import Base

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Check PostgreSQL and create the tables if they don't exist yet
    Base.metadata.create_all(bind=engine)       
    yield

app = FastAPI(title="AI Chatbot - Active Prototype", lifespan=lifespan)

# CONFIGURE CORS PERMISSIONS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], 
    allow_credentials=True,
    allow_methods=["*"],   
    allow_headers=["*"],     
)

app.include_router(chat.router)

