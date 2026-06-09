import pdfplumber
import io
import base64
from PIL import Image
import os
from paddleocr import PPStructure
from groq import AsyncGroq
import numpy as np

groq_client = AsyncGroq()
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct" 
structure_engine = PPStructure(show_log=False, lang='en', enable_mkldnn=False)

class PDFService:
    @classmethod
    async def route_pdf_pages(cls, file_bytes: bytes) -> list:
        """
        Analyzes pages and determines layout type flags
        """
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
        """
        Submits cropped image snippets directly to Groq Vision API for captioning
        """
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
    async def process_hybrid_page(cls, file_bytes: bytes, page_num: int) -> str:
        """
        Combines Ordered Text, PaddleOCR Tables, and Groq Image Descriptions
        """
        print(f"--- [DEBUG] Starting Hybrid Processing for Page {page_num} ---")
        
        supplementary_data = []
        
        # 1. Open the PDF from the raw uploaded bytes
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            page = pdf.pages[page_num - 1]
            
            # 2. Grab text naturally (pdfplumber preserves reading order beautifully)
            clean_text = page.extract_text() or ""
            
            # 3. Turn the page into an image array for PaddleOCR
            # resolution=150 is the perfect balance of speed and OCR accuracy
            page_image = page.to_image(resolution=150).original
            img_np = np.array(page_image)
            
            # 4. Run Stable PaddleOCR V2
            layout_results = structure_engine(img_np)
            
            for region in layout_results:
                region_type = region.get('type', '').lower()
                bbox = region.get('bbox')
                
                # 1. Capture Structural Matrix Tables
                if region_type == 'table' and 'res' in region:
                    html_table = region['res'].get('html', '')
                    supplementary_data.append(f"\n[Extracted Structural Matrix Table]:\n{html_table}\n")
                
                # 2. Capture and Crop Visual Diagrams / Photos for Groq Vision
                elif region_type == 'figure' and bbox:
                    # Crop the PIL image directly
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
                            
                    if text_content.strip():
                        supplementary_data.append(f"\n[Scanned OCR Text]:\n{text_content.strip()}\n")

        page_context = f"--- Document Page {page_num} Context ---\nTEXT ON PAGE:\n{clean_text}\n"
        if supplementary_data:
            page_context += "\nEXTRACTED VISUAL LAYOUT ELEMENTS:\n" + "\n".join(supplementary_data)
            
        return page_context