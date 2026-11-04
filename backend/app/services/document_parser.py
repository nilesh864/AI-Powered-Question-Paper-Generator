from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    page_count: int | None


async def parse_document(filename: str, content: bytes) -> ExtractionResult:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        import pymupdf

        with pymupdf.open(stream=content, filetype="pdf") as document:
            pages = [page.get_text("text").strip() for page in document]
            return ExtractionResult("\n\n".join(text for text in pages if text), len(pages))
    if suffix == ".docx":
        from docx import Document
        from io import BytesIO

        document = Document(BytesIO(content))
        paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        table_rows = [" | ".join(cell.text.strip() for cell in row.cells) for table in document.tables for row in table.rows]
        return ExtractionResult("\n".join([*paragraphs, *[row for row in table_rows if row.strip(" | ")]]), None)
    if suffix == ".pptx":
        from io import BytesIO
        from pptx import Presentation

        presentation = Presentation(BytesIO(content))
        slide_text = []
        for slide in presentation.slides:
            items = []
            for shape in slide.shapes:
                if getattr(shape, "has_text_frame", False) and shape.text.strip():
                    items.append(shape.text)
                if getattr(shape, "has_table", False):
                    items.extend(" | ".join(cell.text.strip() for cell in row.cells) for row in shape.table.rows)
            slide_text.append("\n".join(items))
        return ExtractionResult("\n\n".join(slide_text), len(presentation.slides))
    if suffix in {".txt", ".md"}:
        return ExtractionResult(content.decode("utf-8", errors="replace"), None)
    raise ValueError("Supported formats are PDF, DOCX, PPTX, TXT, and Markdown.")