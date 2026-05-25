from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.api.endpoints import chat
from app.core.database import engine
from app.models import Base

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Check PostgreSQL and create the tables if they don't exist yet
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="AI Chatbot - Active Prototype", lifespan=lifespan)

app.include_router(chat.router)

