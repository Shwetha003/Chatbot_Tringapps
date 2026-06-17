import json
from app.models.document import PageData, TableData


class DocumentConverter:

    @classmethod
    def to_markdown(cls, pages: list[PageData]) -> str:
        blocks = []

        for page in pages:
            if page.route == "blank":
                continue

            blocks.append(f"# Page {page.page_number}\n")

            body = cls._merge_text(page)

            if body:
                blocks.append(body)

            for fig in page.figures:
                blocks.append(f"> **Figure:** {fig.caption}\n")

            for table in page.tables:
                blocks.append(cls._table_to_markdown(table))

        return "\n".join(blocks).strip()


    @classmethod
    def to_json(cls, pages: list[PageData]) -> dict:
        return {
            "pages": [
                cls._page_to_dict(p)
                for p in pages
            ]
        }


    @classmethod
    def to_json_string(cls, pages: list[PageData]) -> str:
        return json.dumps(
            cls.to_json(pages),
            indent=2,
            ensure_ascii=False
        )


    @classmethod
    def _merge_text(cls, page: PageData) -> str:
        lines = []

        if page.text:
            lines.append(page.text.strip())

        for block in page.ocr_text_blocks:
            cleaned = block.strip()

            if cleaned and cleaned not in page.text:
                lines.append(cleaned)

        return "\n\n".join(lines)


    @classmethod
    def _table_to_markdown(cls, table: TableData) -> str:

        if not table.headers and not table.rows:
            return ""

        headers = [
            str(h).strip() if h else ""
            for h in table.headers
        ]

        rows = [
            [
                str(cell).strip() if cell else ""
                for cell in row
            ]
            for row in table.rows
        ]

        col_count = max(
            len(headers),
            max((len(r) for r in rows), default=0)
        )

        def pad(row, n):
            return row + [""] * (n - len(row))

        headers = pad(headers, col_count)

        separator = ["---"] * col_count

        md_rows = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(separator) + " |"
        ]

        for row in rows:
            md_rows.append(
                "| " + " | ".join(
                    pad(row, col_count)
                ) + " |"
            )

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