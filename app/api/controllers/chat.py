from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.chat import UserPayload
from app.crud import chat as crud_chat
from app.services import llm_service
from app.services.pdf_service import PDFService
import io
import pdfplumber

router = APIRouter(prefix="/api")

@router.get("/conversation/new")
async def start_new_chat_session(db: Session = Depends(get_db)):
    try:
        new_conv_id = crud_chat.create_new_conversation(db)
        return {"conversation_id": new_conv_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat")
async def process_chatbot_message(
    payload: UserPayload = Depends(UserPayload.as_form),
    chat_file: UploadFile = File(None),
    db: Session = Depends(get_db)):

    try:
        pdf_context = ""

        if chat_file and chat_file.filename.endswith('.pdf'):
            file_bytes = await chat_file.read()

            #Page Type Router
            page_report = await PDFService.route_pdf_pages(file_bytes)
            print(f"DEBUG - PDF Route Layout Report: {page_report}")

            extracted_blocks = []
            
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in page_report:
                    page_num = page["page_number"]
                    route = page["assigned_route"]

                    # Route A: Pure text (Instant extraction, skips AI layers)
                    if route == "text_heavy":
                        page_obj = pdf.pages[page_num - 1]
                        text = page_obj.extract_text() or ""
                        extracted_blocks.append(f"-- Page {page_num} --\n{text}")

                    # Route B: Complex layouts / Scans (Headed to PaddleOCR + Groq Vision)
                    elif route == "hybrid":
                        hybrid_context = await PDFService.process_hybrid_page(file_bytes, page_num)
                        extracted_blocks.append(hybrid_context)
            
            if extracted_blocks:
                pdf_context = "\n\n".join(extracted_blocks)

        if not payload.message and chat_file:
            payload.message = "Analyze this uploaded document, summarize its contents, and tell me what actions I can take."

        # Pass compiled thread to Groq core layer

        bot_reply=await llm_service.generate_bot_reply(db=db, payload=payload, context=pdf_context)

        return {
            "status": "success",
            "conversation_id": payload.conversation_id,
            "session_id": payload.session_id,
            "bot_reply": bot_reply
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
