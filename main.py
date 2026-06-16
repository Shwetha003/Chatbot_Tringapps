import sys
import os
os.environ["FLAGS_use_onednn"] = "0"
os.environ["FLAGS_allocator_strategy"] = "naive_best_fit"
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api.controllers import chat
from app.core.database import engine
from app.models import Base

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)       
    yield

app = FastAPI(title="AI Chatbot - Active Prototype", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],   
    allow_headers=["*"],     
)

app.include_router(chat.router)