import io
import re
import logging
import pdfplumber
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from app.schemas.chat import UserPayload
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services import llm_service
from app.services.crawler import scrape_to_pure_text
from app.services.pdf_service import PDFService
from app.services.document_converter import DocumentConverter
from app.models.chat import Document, Chunk, ChatMessage 
from app.models.document import PageData
from app.crud import chat as crud_chat

logger = logging.getLogger(__name__)

# Use a clean prefix to avoid repeating sub-paths like /api/chat/chat
router = APIRouter(prefix="/api")

MAX_PDF_BYTES = 20 * 1024 * 1024


@router.get("/conversation/new")
async def start_new_chat_session(db: Session = Depends(get_db)):
    try:
        new_conv_id = crud_chat.create_new_conversation(db)
        return {"conversation_id": new_conv_id}
    except Exception as e:
        logger.exception("Failed to create new conversation")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/crawl")
async def process_crawl_request(
    url: str = Form(..., description="Paste a website URL to crawl"),
    conversation_id: int = Form(..., description="Conversation ID"),
    session_id: int = Form(..., description="Session ID"),
    db: Session = Depends(get_db)
):
    try:
        url_match = re.search(r'(https?://[^\s]+)', url)
        if not url_match:
            raise HTTPException(status_code=400, detail="Provided text is not a valid URL.")
            
        target_url = url_match.group(0)
        scraped_text = await scrape_to_pure_text(target_url)
        
        existing_entry = db.query(Document).filter(Document.source_url == target_url).first()
        if not existing_entry:
            db_doc = Document(
                document_name=target_url, 
                source_url=target_url,
                file_type="url",
                chunk_count=1  
            )
            db.add(db_doc)
            db.commit()
            db.refresh(db_doc)

            db_chunk = Chunk(
                doc_id=db_doc.document_id,  
                chunk_content=scraped_text,  
                embedding=None               
            )
            db.add(db_chunk)
            db.commit()

        user_msg = ChatMessage(
            conversation_id=conversation_id,
            session_id=session_id,
            sender_type="user",
            content=f"Crawled URL: {target_url}"
        )
        bot_msg = ChatMessage(
            conversation_id=conversation_id,
            session_id=session_id,
            sender_type="bot",
            content=scraped_text
        )
        db.add(user_msg)
        db.add(bot_msg)
        db.commit()

        return {
            "status": "success",
            "conversation_id": conversation_id,
            "session_id": session_id,
            "bot_reply": scraped_text,
            "document_json": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error during crawl route execution")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")


@router.post("/chat")
async def process_chatbot_message(
    chat_file: UploadFile = File(None),
    conversation_id: int = Form(..., description="Conversation ID"),
    session_id: int = Form(..., description="Session ID"),
    message: str = Form(None, description="User text message"),
    db: Session = Depends(get_db)
):
    try:
        payload = UserPayload(
            conversation_id=conversation_id,
            session_id=session_id,
            message=message
        )
        
        pdf_markdown = ""
        pdf_json = {}

        if chat_file and chat_file.filename.endswith('.pdf'):
            file_bytes = await chat_file.read(MAX_PDF_BYTES + 1)
            if len(file_bytes) > MAX_PDF_BYTES:
                raise HTTPException(status_code=413, detail="PDF exceeds 20 MB limit")

            page_report = await PDFService.route_pdf_pages(file_bytes)
            collected_pages: list[PageData] = []
            
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in page_report:
                    page_num = page["page_number"]
                    route = page["assigned_route"]

                    if route == "text_heavy":
                        page_obj = pdf.pages[page_num - 1]
                        text = page_obj.extract_text() or ""
                        collected_pages.append(
                            PageData(page_number=page_num, route="text_heavy", text=text)
                        )
                    elif route == "hybrid":
                        page_data = await PDFService.process_hybrid_page(file_bytes, page_num)
                        collected_pages.append(page_data)

            pdf_markdown = DocumentConverter.to_markdown(collected_pages)
            pdf_json = DocumentConverter.to_json(collected_pages)
            
            crud_chat.save_parsed_document_data(
                db=db, 
                conversation_id=payload.conversation_id, 
                markdown_text=pdf_markdown, 
                json_dict=pdf_json
            )
            
            try:
                crud_chat.create_document_record(
                    db=db,
                    document_name=chat_file.filename,
                    file_type="pdf",
                    source_url=None,
                    chunk_count=len(collected_pages)
                )
            except Exception as doc_err:
                logger.warning(f"Failed to record document tracking metadata: {doc_err}")

        if not payload.message and chat_file:
            payload.message = "Analyze this uploaded document, summarize its contents, and tell me what actions I can take."

        bot_reply = await llm_service.generate_bot_reply(db=db, payload=payload, context=pdf_markdown)

        return {
            "status": "success",
            "conversation_id": payload.conversation_id,
            "session_id": payload.session_id,
            "bot_reply": bot_reply,
            "document_json": pdf_json if pdf_json else None,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in process_chatbot_message")
        raise HTTPException(status_code=500, detail="An internal error occurred")