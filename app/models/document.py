from dataclasses import dataclass, field
from typing import Optional

@dataclass
class TableData:
    headers: list[str]
    rows: list[list[str]]
    raw_html: str = ""

@dataclass
class FigureData:
    caption: str
    bbox: Optional[list[float]] = None

@dataclass
class PageData:
    page_number: int
    route: str                              # "text_heavy" | "hybrid" | "blank"
    text: str = ""
    tables: list[TableData] = field(default_factory=list)
    figures: list[FigureData] = field(default_factory=list)
    ocr_text_blocks: list[str] = field(default_factory=list)