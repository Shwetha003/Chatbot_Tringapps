import json
from app.models.document import PageData, TableData

class DocumentConverter:
    """
    Converts a list of PageData objects into:
      - A markdown string  (for LLM context injection)
      - A JSON-serializable dict  (for structured storage / targeted queries)
    """

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    @classmethod
    def to_markdown(cls, pages: list[PageData]) -> str:
        blocks: list[str] = []
        for page in pages:
            if page.route == "blank":
                continue
            blocks.append(f"# Page {page.page_number}\n")

            # 1. Narrative text (from pdfplumber or OCR)
            body = cls._merge_text(page)
            if body:
                blocks.append(body)

            # 2. Figures — inline where they appeared
            for fig in page.figures:
                blocks.append(f"> **Figure:** {fig.caption}\n")

            # 3. Tables as markdown tables
            for table in page.tables:
                blocks.append(cls._table_to_markdown(table))

        return "\n".join(blocks).strip()

    @classmethod
    def to_json(cls, pages: list[PageData]) -> dict:
        return {
            "pages": [cls._page_to_dict(p) for p in pages]
        }

    @classmethod
    def to_json_string(cls, pages: list[PageData]) -> str:
        return json.dumps(cls.to_json(pages), indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    @classmethod
    def _merge_text(cls, page: PageData) -> str:
        """
        Combine pdfplumber text + OCR text blocks, deduplicating near-identical
        lines (OCR often re-extracts text that pdfplumber already got).
        """
        lines: list[str] = []

        if page.text:
            lines.append(page.text.strip())

        for block in page.ocr_text_blocks:
            cleaned = block.strip()
            # Skip if this block is already substantially covered by pdfplumber text
            if cleaned and cleaned not in page.text:
                lines.append(cleaned)

        return "\n\n".join(lines)

    @classmethod
    def _table_to_markdown(cls, table: TableData) -> str:
        if not table.headers and not table.rows:
            return ""

        # Normalise column count across all rows
        col_count = max(
            len(table.headers),
            max((len(r) for r in table.rows), default=0)
        )

        def pad(row: list[str], n: int) -> list[str]:
            return row + [""] * (n - len(row))

        headers = pad(table.headers, col_count) if table.headers else [""] * col_count
        separator = ["---"] * col_count

        md_rows = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(separator) + " |",
        ]
        for row in table.rows:
            md_rows.append("| " + " | ".join(pad(row, col_count)) + " |")

        return "\n".join(md_rows) + "\n"

    @classmethod
    def _page_to_dict(cls, page: PageData) -> dict:
        return {
            "page_number": page.page_number,
            "route": page.route,
            "text": page.text,
            "ocr_text_blocks": page.ocr_text_blocks,
            "figures": [
                {
                    "caption": fig.caption,
                    "bbox": fig.bbox,
                }
                for fig in page.figures
            ],
            "tables": [
                {
                    "headers": table.headers,
                    "rows": table.rows,
                }
                for table in page.tables
            ],
        }