import io
import base64
import pdfplumber
from paddleocr import PPStructure
from groq import AsyncGroq

from app.services.embedding_services import create_embedding
from app.models.document import PageData, TableData
from app.services.chunking import create_chunks
from app.crud.chat import save_chunk

print("PDF_SERVICE START")
groq_client = AsyncGroq()
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
_structure_engine = None

def _get_structure_engine():
    global _structure_engine

    if _structure_engine is None:
        _structure_engine = PPStructure(
            show_log=False,
            lang="en",
            layout=False,
            enable_mkldnn=False,
            cpu_threads=1
        )
    return _structure_engine

class PDFService:
    @classmethod
    async def route_pdf_pages(cls, file_bytes: bytes):
        route_report = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:

            for i, page in enumerate(pdf.pages):
                clean_text = page.extract_text() or ""
                char_count = len(clean_text.strip())
                has_images = len(page.images) > 0
                has_tables = len(page.find_tables()) > 0
                if has_images or has_tables or char_count == 0:
                    assigned_route = "hybrid"
                else:
                    assigned_route = "text_heavy"
                route_report.append(
                    {
                        "page_number": i + 1,
                        "assigned_route": assigned_route,
                        "character_count": char_count,
                        "contains_images": has_images,
                        "contains_tables": has_tables
                    }
                )
        return route_report

    @classmethod
    async def _get_image_caption_from_groq(
        cls,
        base64_image_str: str
    ):
        try:
            response = await groq_client.chat.completions.create(
                model=VISION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text":
                                "Analyze this cropped diagram, chart, or graphic from a document. Describe its contents, data trends, or structural text layout in precise analytical detail."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url":
                                    f"data:image/png;base64,{base64_image_str}"
                                }
                            }
                      ]
                    }
                ],
                temperature=0.2,
                max_tokens=300
            )
            return response.choices[0].message.content
        except Exception as e:
            print(
                f"[ERROR] Groq Vision API failed: {e}"
            )

            return f"[Error generating image caption: {str(e)}]"

    @classmethod
    async def process_hybrid_page(
        cls,
        file_bytes: bytes,
        page_num: int
    ):
        print(
            f"--- [DEBUG] Starting Hybrid Processing for Page {page_num} ---"
        )
        page_data = PageData(
            page_number=page_num,
            route="hybrid"
        )
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            page = pdf.pages[page_num - 1]
            page_data.text = page.extract_text() or ""
            tables = page.find_tables()
            for table in tables:
                table_matrix = table.extract()
                if table_matrix:
                    headers = [
                                str(cell).strip() if cell else ""
                                for cell in table_matrix[0]
]
                    rows = [
                          [
                                str(cell).strip() if cell else ""
                                for cell in row
    ]
                          for row in table_matrix[1:]
]
                    page_data.tables.append(
                        TableData(
                            headers=headers,
                            rows=rows,
                            raw_html=str(table_matrix)
                        )
                    )
            if not page_data.text.strip():
                page_image = page.to_image(
                    resolution=150
                ).original
                buffer = io.BytesIO()
                page_image.save(
                    buffer,
                    format="PNG"
                )
                img_base64 = base64.b64encode(
                    buffer.getvalue()
                ).decode()
                caption = await cls._get_image_caption_from_groq(
                    img_base64
                )
                page_data.ocr_text_blocks.append(
                    caption
                )
        return page_data

    @classmethod
    async def save_pdf_chunks(
        cls,
        pages,
        db,
        document_id
    ):
        print(
            "========== SAVE PDF CHUNKS  =========="
        )
        full_text = ""
        for page in pages:
            if page.text:
                full_text += page.text + "\n"
            for ocr in page.ocr_text_blocks:
                full_text += ocr + "\n"

        chunks = create_chunks(full_text)
        print(
            "TOTAL CHUNKS CREATED:",
            len(chunks)
        )

        for chunk in chunks:
            print(
                "SAVING CHUNK:",
                chunk[:50]
            )
            vector = create_embedding(chunk)
            save_chunk(
                db=db,
                document_id=document_id,
                chunk_content=chunk,
                embedding=vector
            )

        return len(chunks)

    @classmethod
    async def process_pdf_and_save_chunks(
        cls,
        file_bytes,
        db,
        document_id
    ):
        route_report = await cls.route_pdf_pages(
            file_bytes
        )
        pages = []
        for page_info in route_report:
            page = await cls.process_hybrid_page(
                file_bytes,
                page_info["page_number"]
            )
            pages.append(page)

        chunk_count = await cls.save_pdf_chunks(
            pages,
            db,
            document_id
        )

        print(
            f"Saved {chunk_count} chunks for document {document_id}"
        )
        return pages