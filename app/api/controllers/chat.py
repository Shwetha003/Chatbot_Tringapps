from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.chat import UserPayload
from app.crud import chat as crud_chat
from app.services import llm_service
from app.services.pdf_service import PDFService
from app.services.document_converter import DocumentConverter
from app.models.document import PageData
import io
import pdfplumber
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB

@router.get("/conversation/new")
async def start_new_chat_session(db: Session = Depends(get_db)):
    try:
        new_conv_id = crud_chat.create_new_conversation(db)
        return {"conversation_id": new_conv_id}
    except Exception as e:
        logger.exception("Failed to create new conversation")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat")
async def process_chatbot_message(
    payload: UserPayload = Depends(UserPayload.as_form),
    chat_file: UploadFile = File(None),
    db: Session = Depends(get_db)):

    try:
        pdf_markdown = ""
        pdf_json = {}

        if chat_file and chat_file.filename.endswith('.pdf'):
            file_bytes = await chat_file.read(MAX_PDF_BYTES + 1)
            if len(file_bytes) > MAX_PDF_BYTES:
                raise HTTPException(status_code=413, detail="PDF exceeds 20 MB limit")

            # Page Type Router
            page_report = await PDFService.route_pdf_pages(file_bytes)
            print(f"DEBUG - PDF Route Layout Report: {page_report}")

            collected_pages: list[PageData] = []
            
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in page_report:
                    page_num = page["page_number"]
                    route = page["assigned_route"]

                    # Route A: Pure text (Instant extraction, skips AI layers)
                    if route == "text_heavy":
                        page_obj = pdf.pages[page_num - 1]
                        text = page_obj.extract_text() or ""
                        collected_pages.append(
                            PageData(page_number=page_num, route="text_heavy", text=text)
                        )
                    # Route B: Complex layouts / Scans (Headed to PaddleOCR + Groq Vision)
                    elif route == "hybrid":
                        page_data = await PDFService.process_hybrid_page(file_bytes, page_num)
                        collected_pages.append(page_data)

            # --- Convert to markdown + JSON ---
            pdf_markdown = DocumentConverter.to_markdown(collected_pages)
            pdf_json = DocumentConverter.to_json(collected_pages)
            
            crud_chat.save_parsed_document_data(
                db=db, 
                conversation_id=payload.conversation_id, 
                markdown_text=pdf_markdown, 
                json_dict=pdf_json
            )
            print(f"DEBUG - Parsed markdown length: {len(pdf_markdown)} chars")
            print(f"DEBUG - JSON page count: {len(pdf_json.get('pages', []))}")

            
            try:
                crud_chat.create_document_record(
                    db=db,
                    document_name=chat_file.filename,
                    file_type="pdf",
                    source_url=None,  # Set if handling URL inputs later
                    chunk_count=len(collected_pages)  # Tracking total parsed pages as chunks for now
                )
                print(f"✅ Success - Logged metadata for {chat_file.filename} to database.")
            except Exception as doc_err:
                logger.warning(f"Failed to record document tracking metadata: {doc_err}")

        if not payload.message and chat_file:
            payload.message = "Analyze this uploaded document, summarize its contents, and tell me what actions I can take."

        # Pass compiled thread to Groq core layer
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