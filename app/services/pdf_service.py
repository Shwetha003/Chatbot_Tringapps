import pdfplumber
import io
import base64
from PIL import Image
import os
from paddleocr import PPStructure
from groq import AsyncGroq
import numpy as np
from bs4 import BeautifulSoup


from app.models.document import PageData, TableData, FigureData

groq_client = AsyncGroq()
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct" 

# Lazy singleton — initialised only on first PDF request, not at import time
_structure_engine = None
 
def _get_structure_engine():
    global _structure_engine
    if _structure_engine is None:
        _structure_engine = PPStructure(show_log=False, lang='en', enable_mkldnn=False)
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
                
                # Check for physical layout objects embedded in the PDF
                has_images = len(page.images) > 0
                has_tables = len(page.find_tables()) > 0
                
                # If it has visual objects OR contains absolutely zero digital text (scanned page),
                # send it to the hybrid pipeline so PaddleOCR can run OCR/Vision analysis.
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

        # ------------------------------------------------------------------ #
    #  HTML table → TableData                                              #
    # ------------------------------------------------------------------ #
 
    @classmethod
    def _parse_html_table(cls, html: str) -> TableData:
        """
        Converts PaddleOCR's HTML table string into a structured TableData.
        The first <tr> is treated as headers if it contains <th> elements,
        otherwise the first row is used as headers.
        """
        soup = BeautifulSoup(html, "html.parser")
        rows_raw = soup.find_all("tr")
 
        if not rows_raw:
            return TableData(headers=[], rows=[], raw_html=html)
 
        headers: list[str] = []
        rows: list[list[str]] = []
 
        first_row = rows_raw[0]
        th_cells = first_row.find_all("th")
 
        if th_cells:
            headers = [th.get_text(strip=True) for th in th_cells]
            data_rows = rows_raw[1:]
        else:
            # No <th> — treat first row as header
            td_cells = first_row.find_all("td")
            headers = [td.get_text(strip=True) for td in td_cells]
            data_rows = rows_raw[1:]
 
        for tr in data_rows:
            cells = tr.find_all(["td", "th"])
            rows.append([c.get_text(strip=True) for c in cells])
 
        return TableData(headers=headers, rows=rows, raw_html=html)


    @classmethod
    async def process_hybrid_page(cls, file_bytes: bytes, page_num: int) -> str:
        """
        Combines Ordered Text, PaddleOCR Tables, and Groq Image Descriptions
        """
        supplementary_data = []
        print(f"--- [DEBUG] Starting Hybrid Processing for Page {page_num} ---")
        
        page_data = PageData(page_number=page_num, route="hybrid")
        
        # 1. Open the PDF from the raw uploaded bytes
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            page = pdf.pages[page_num - 1]
            
            # 2. Grab text naturally (pdfplumber preserves reading order beautifully)
            page_data.text = page.extract_text() or ""
            
            # 3. Turn the page into an image array for PaddleOCR
            # resolution=150 is the perfect balance of speed and OCR accuracy
            page_image = page.to_image(resolution=150).original
            img_np = np.array(page_image)
            
            # 4. Run Stable PaddleOCR V2
            structure_engine = _get_structure_engine()
            layout_results = structure_engine(img_np)
            
            for region in layout_results:
                region_type = region.get('type', '').lower()
                bbox = region.get('bbox')
                
                # 1. Capture Structural Matrix Tables
                if region_type == 'table' and 'res' in region:
                    html_table = region['res'].get('html', '')
                    if html_table:
                        table_data = cls._parse_html_table(html_table)
                        page_data.tables.append(table_data)
                
                # 2. Capture and Crop Visual Diagrams / Photos for Groq Vision
                elif region_type == 'figure' and bbox:
                    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                        page_image = pdf.pages[page_num - 1].to_image(resolution=150).original

                    cropped_region = page_image.crop((bbox[0], bbox[1], bbox[2], bbox[3]))
                    buffered = io.BytesIO()
                    cropped_region.save(buffered, format="PNG")
                    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                    
                    caption = await cls._get_image_caption_from_groq(img_base64)
                    supplementary_data.append(f"\n[Visual Element Description]:\n{caption}\n")

                # 3. Capture Scanned Paragraphs / Document Titles (OCR)
                elif region_type in ['text', 'title'] and 'res' in region:
                    text_content = ""
                    for line in region['res']:
                        if isinstance(line, dict) and 'text' in line:
                            text_content += line['text'] + " "
                            
                    cleaned = text_content.strip()
                    if cleaned:
                        page_data.ocr_text_blocks.append(cleaned)

        return page_data