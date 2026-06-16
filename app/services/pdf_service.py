import io
import base64
import os
import pdfplumber
import numpy as np
from PIL import Image
from paddleocr import PPStructure
from groq import AsyncGroq

from app.models.document import PageData, TableData, FigureData

groq_client = AsyncGroq()
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct" 

# Lazy singleton — initialised safely for Windows environment compliance
_structure_engine = None
 
def _get_structure_engine():
    global _structure_engine
    if _structure_engine is None:
       
        _structure_engine = PPStructure(
            show_log=False, 
            lang='en', 
            layout=False,
            enable_mkldnn=False,
            cpu_threads=1
        )
    return _structure_engine


class PDFService:
    @classmethod
    async def route_pdf_pages(cls, file_bytes: bytes) -> list:
        """ Analyzes pages and determines layout type flags """
        route_report = []
        
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                clean_text = page.extract_text() or ""
                char_count = len(clean_text.strip())
                
                has_images = len(page.images) > 0
                has_tables = len(page.find_tables()) > 0
                
                if has_images or has_tables or char_count == 0:
                    assigned_route = 'hybrid'
                elif char_count > 0:
                    assigned_route = 'text_heavy'
                else:
                    assigned_route = 'blank'
                    
                route_report.append({
                    'page_number': i + 1,
                    'assigned_route': assigned_route,
                    'character_count': char_count,
                    'contains_images': has_images,
                    'contains_tables': has_tables
                })
            
        print(f"DEBUG - Intelligent Route Layout Report:\n{route_report}")
        return route_report
    
    @classmethod
    async def _get_image_caption_from_groq(cls, base64_image_str: str) -> str:
        """Submits cropped image snippets directly to Groq Vision API for captioning """
        try:
            response = await groq_client.chat.completions.create(
                model=VISION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Analyze this cropped diagram, chart, or graphic from a document. Describe its contents, data trends, or structural text layout in precise analytical detail."},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image_str}"}}
                        ]
                    }
                ],
                temperature=0.2,
                max_tokens=300
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[ERROR] Groq Vision API failed: {e}")
            return f"[Error generating image caption description: {str(e)}]"

    @classmethod
    async def process_hybrid_page(cls, file_bytes: bytes, page_num: int) -> PageData:
        """
        Combines Ordered Text (pdfplumber) and Groq Image Descriptions natively
        while leveraging safe PaddleOCR text processing wrappers.
        """
        supplementary_data = []
        print(f"--- [DEBUG] Starting Hybrid Processing for Page {page_num} ---")
        
        page_data = PageData(page_number=page_num, route="hybrid")
        
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            page = pdf.pages[page_num - 1]
            page_data.text = page.extract_text() or ""
            
            # Extract structural tables natively via pdfplumber
            tables = page.find_tables()
            for table in tables:
                table_matrix = table.extract()
                if table_matrix and len(table_matrix) > 0:
                    headers = [str(cell).strip() if cell else "" for cell in table_matrix[0]]
                    data_rows = []
                    for row in table_matrix[1:]:
                        data_rows.append([str(cell).strip() if cell else "" for cell in row])
                        
                    html_fallback = "<table>"
                    html_fallback += "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"
                    for r in data_rows:
                        html_fallback += "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
                    html_fallback += "</table>"
                    
                    page_data.tables.append(
                        TableData(headers=headers, rows=data_rows, raw_html=html_fallback)
                    )
            
            # If it's a completely scanned page layout, run pure image fallback to Groq Vision
            if not page_data.text.strip():
                page_image = page.to_image(resolution=150).original
                buffered = io.BytesIO()
                page_image.save(buffered, format="PNG")
                img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                
                caption = await cls._get_image_caption_from_groq(img_base64)
                page_data.ocr_text_blocks.append(caption)
                
            # Process sub-element crops using native page images properties 
            else:
                for img_obj in page.images:
                    try:
                        bbox = (img_obj["x0"], img_obj["top"], img_obj["x1"], img_obj["bottom"])
                        page_image = page.to_image(resolution=150).original
                        cropped_region = page_image.crop(bbox)
                        
                        buffered = io.BytesIO()
                        cropped_region.save(buffered, format="PNG")
                        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                        
                        caption = await cls._get_image_caption_from_groq(img_base64)
                        
                        element_str = f"\n[Visual Element Description]:\n{caption}\n"
                        supplementary_data.append(element_str)
                        page_data.ocr_text_blocks.append(element_str)
                    except Exception:
                        continue

            # Keep Paddle active in memory without using layout parsing engines
            _ = _get_structure_engine()

        return page_data