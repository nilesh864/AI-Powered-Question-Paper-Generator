from datetime import datetime, timezone
from io import BytesIO
import re
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.shared import Inches, Pt
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.paper import GeneratedPaper, clean_print_text


SECTION_TITLES = {
    "MCQ": "A) Select the correct option.",
    "Short Answer": "B) Write short notes on.",
    "Long Answer": "C) Answer the following questions.",
    "Case Study": "D) Read the case and answer the questions.",
}


def _question_groups(paper: GeneratedPaper):
    types = dict.fromkeys(question.question_type for question in paper.questions)
    return [(question_type, [(index, question) for index, question in enumerate(paper.questions) if question.question_type == question_type]) for question_type in types]


def _instructions(paper: GeneratedPaper) -> list[str]:
    return paper.instructions or [
        "All questions are compulsory.",
        "Marks are indicated against each question.",
        "Illustrate your answers with neat sketches wherever necessary.",
    ]


def _paper_metadata(paper: GeneratedPaper) -> list[list[tuple[str, str]]]:
    course_title = paper.course_title or paper.subject
    program = paper.program_name or "-"
    semester = paper.semester or "-"
    return [
        [("Program", program), ("Sem", semester)],
        [("Course", course_title), ("Course Code", paper.course_code or "-")],
        [("Marks", str(paper.total_marks)), ("Time", _format_duration(paper.duration_minutes))],
    ]


def _format_duration(duration_minutes: int) -> str:
    hours, minutes = divmod(duration_minutes, 60)
    if hours and minutes:
        return f"{hours} hr {minutes} mins"
    if hours:
        return f"{hours} {'hr' if hours == 1 else 'hrs'}"
    return f"{minutes} mins"


def _official_header(paper: GeneratedPaper, university: str, title: str, styles) -> list:
    story = [
        Paragraph(escape(university.upper()), styles["OfficialUniversity"]),
        Paragraph(escape(paper.institution_address or "Aurangabad-431003"), styles["OfficialAddress"]),
        Paragraph(escape(paper.exam_type), styles["OfficialExam"]),
        Paragraph(escape(title), styles["OfficialTitle"]),
    ]
    metadata_rows = []
    for left, right in _paper_metadata(paper):
        metadata_rows.append([
            Paragraph(f"<b>{escape(left[0])}:</b> {escape(left[1])}", styles["OfficialMeta"]),
            Paragraph(f"<b>{escape(right[0])}:</b> {escape(right[1])}", styles["OfficialMeta"]),
        ])
    metadata = Table(metadata_rows, colWidths=[83 * mm, 83 * mm], hAlign="CENTER")
    metadata.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#555555")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([metadata, Spacer(1, 4 * mm)])
    return story


def _page_chrome(paper: GeneratedPaper):
    def decorate(canvas, document):
        canvas.saveState()
        canvas.setTitle(f"{paper.course_title or paper.subject} - {paper.exam_type}")
        canvas.setAuthor(paper.university_name)
        canvas.setSubject("University examination document")
        canvas.setFont("Times-Roman", 8)
        canvas.setFillColor(colors.HexColor("#333333"))
        canvas.drawCentredString(A4[0] / 2, 10 * mm, f"{paper.course_code or paper.subject}  |  Page {document.page}")
        canvas.restoreState()

    return decorate


def build_exam_pdf(paper: GeneratedPaper, institution: str = "MGM UNIVERSITY", teacher_name: str = "Teacher") -> bytes:
    del teacher_name
    university = paper.university_name or institution
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=22 * mm,
        leftMargin=22 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="OfficialUniversity", parent=styles["Title"], fontName="Times-Bold", alignment=TA_CENTER, fontSize=16, leading=19, spaceAfter=1, textColor=colors.black))
    styles.add(ParagraphStyle(name="OfficialAddress", parent=styles["Normal"], fontName="Times-Roman", alignment=TA_CENTER, fontSize=10, leading=12, spaceAfter=5))
    styles.add(ParagraphStyle(name="OfficialExam", parent=styles["Heading2"], fontName="Times-Bold", alignment=TA_CENTER, fontSize=12, leading=15, spaceBefore=2, spaceAfter=8))
    styles.add(ParagraphStyle(name="OfficialTitle", parent=styles["Heading2"], fontName="Times-Bold", alignment=TA_CENTER, fontSize=13, leading=16, spaceBefore=0, spaceAfter=7))
    styles.add(ParagraphStyle(name="OfficialMeta", parent=styles["BodyText"], fontName="Times-Roman", fontSize=10, leading=13))
    styles.add(ParagraphStyle(name="OfficialInstruction", parent=styles["BodyText"], fontName="Times-Roman", fontSize=10, leading=13))
    styles.add(ParagraphStyle(name="OfficialSection", parent=styles["Heading3"], fontName="Times-Bold", fontSize=11, leading=14, spaceBefore=8, spaceAfter=4, keepWithNext=True))
    styles.add(ParagraphStyle(name="OfficialQuestion", parent=styles["BodyText"], fontName="Times-Roman", fontSize=11, leading=15, spaceAfter=2))
    styles.add(ParagraphStyle(name="OfficialOption", parent=styles["BodyText"], fontName="Times-Roman", fontSize=10, leading=13, leftIndent=8 * mm, spaceAfter=1))

    story = _official_header(paper, university, f"QUESTION PAPER · SET {paper.set_label}", styles)

    instruction_rows = [[Paragraph("<b>Instructions to the students</b>", styles["OfficialInstruction"])]]
    instruction_rows.extend([[Paragraph(f"{index}. {escape(line)}", styles["OfficialInstruction"])] for index, line in enumerate(_instructions(paper), start=1)])
    instructions = Table(instruction_rows, colWidths=[166 * mm], hAlign="CENTER")
    instructions.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#555555")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#888888")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([instructions, Spacer(1, 4 * mm)])

    question_number = 1
    for question_type, group in _question_groups(paper):
        story.append(Paragraph(escape(SECTION_TITLES.get(question_type, "Questions")), styles["OfficialSection"]))
        for _, question in group:
            statement = escape(clean_print_text(question.text)).replace("\n", "<br/>")
            heading = Paragraph(f"<b>Q.{question_number}.</b> {statement}", styles["OfficialQuestion"])
            marks = Paragraph(f"({question.marks})", ParagraphStyle(name=f"Marks{question_number}", parent=styles["OfficialQuestion"], alignment=TA_RIGHT, keepTogether=True))
            question_row = Table([[heading, marks]], colWidths=[151 * mm, 15 * mm], hAlign="LEFT")
            question_row.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            question_block = [question_row]
            for option_index, option in enumerate(question.options):
                question_block.append(Paragraph(f"{chr(65 + option_index)}) {escape(clean_print_text(option))}", styles["OfficialOption"]))
            question_block.append(Spacer(1, 2 * mm))
            story.append(KeepTogether(question_block))
            question_number += 1

    decorator = _page_chrome(paper)
    document.build(story, onFirstPage=decorator, onLaterPages=decorator)
    return buffer.getvalue()


def build_exam_docx(paper: GeneratedPaper) -> bytes:
    document = Document()
    section = document.sections[0]
    section.top_margin = Inches(0.65)
    section.bottom_margin = Inches(0.65)
    section.left_margin = Inches(0.85)
    section.right_margin = Inches(0.85)

    normal = document.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(11)

    university = document.add_paragraph()
    university.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = university.add_run((paper.university_name or "MGM UNIVERSITY").upper())
    run.bold = True
    run.font.name = "Times New Roman"
    run.font.size = Pt(16)
    address = document.add_paragraph(paper.institution_address or "Aurangabad-431003")
    address.alignment = WD_ALIGN_PARAGRAPH.CENTER
    exam = document.add_paragraph()
    exam.alignment = WD_ALIGN_PARAGRAPH.CENTER
    exam_run = exam.add_run(f"{paper.exam_type}  |  Set {paper.set_label}")
    exam_run.bold = True
    exam_run.font.size = Pt(12)

    metadata = document.add_table(rows=3, cols=2)
    metadata.style = "Table Grid"
    for row, (left, right) in zip(metadata.rows, _paper_metadata(paper)):
        for cell, item in zip(row.cells, (left, right)):
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            paragraph = cell.paragraphs[0]
            label = paragraph.add_run(f"{item[0]}: ")
            label.bold = True
            paragraph.add_run(item[1])

    document.add_paragraph()
    instruction_table = document.add_table(rows=1, cols=1)
    instruction_table.style = "Table Grid"
    instruction_cell = instruction_table.cell(0, 0)
    heading = instruction_cell.paragraphs[0]
    heading.add_run("Instructions to the students").bold = True
    for index, line in enumerate(_instructions(paper), start=1):
        instruction_cell.add_paragraph(f"{index}. {line}")
    document.add_paragraph()

    question_number = 1
    for question_type, group in _question_groups(paper):
        section_heading = document.add_paragraph()
        section_heading.paragraph_format.keep_with_next = True
        section_heading.add_run(SECTION_TITLES.get(question_type, "Questions")).bold = True
        for _, question in group:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.keep_together = True
            paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(6.25), WD_TAB_ALIGNMENT.RIGHT)
            number = paragraph.add_run(f"Q.{question_number}. ")
            number.bold = True
            paragraph.add_run(clean_print_text(question.text))
            paragraph.add_run(f"\t({question.marks})")
            for option_index, option in enumerate(question.options):
                option_paragraph = document.add_paragraph()
                option_paragraph.paragraph_format.left_indent = Inches(0.25)
                option_paragraph.paragraph_format.keep_together = True
                option_paragraph.add_run(f"{chr(65 + option_index)}) {clean_print_text(option)}")
            question_number += 1

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _mcq_correct_option(question) -> tuple[str, str] | None:
    options = [clean_print_text(option) for option in question.options]
    if question.correct_option in {"A", "B", "C", "D"}:
        index = ord(question.correct_option) - ord("A")
        if index < len(options):
            return question.correct_option, options[index]
    explicit = re.search(r"(?:correct\s+option|answer)\s*[:\-]?\s*([A-D])\b", question.answer, flags=re.IGNORECASE)
    if explicit:
        index = ord(explicit.group(1).upper()) - ord("A")
        if index < len(options):
            return explicit.group(1).upper(), options[index]
    normalized_answer = clean_print_text(question.answer).casefold()
    for index, option in enumerate(options):
        if option and option.casefold() in normalized_answer:
            return chr(65 + index), option
    return None


def _solution_blocks(answer: str, styles) -> list:
    blocks: list = []
    lines = answer.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    heading_pattern = re.compile(r"^\s*\*\*(.+?)\*\*\s*:?[ \t]*$")
    content_lines: list[str] = []
    pending_heading: str | None = None

    def flush_content() -> None:
        nonlocal content_lines, pending_heading
        normalized = [line.strip() for line in content_lines if line.strip()]
        for offset in range(0, len(normalized), 5):
            chunk = normalized[offset:offset + 5]
            paragraph = Paragraph("<br/>".join(escape(line) for line in chunk), styles["SolutionText"])
            if pending_heading is not None:
                heading = Paragraph(f"<b>{escape(pending_heading)}</b>", styles["SolutionSubheading"])
                blocks.append(KeepTogether([heading, paragraph]))
                pending_heading = None
            else:
                blocks.append(paragraph)
        if not normalized and pending_heading is not None:
            blocks.append(Paragraph(f"<b>{escape(pending_heading)}</b>", styles["SolutionSubheading"]))
            pending_heading = None
        content_lines = []

    for line in lines:
        match = heading_pattern.match(line)
        if match:
            flush_content()
            pending_heading = match.group(1).rstrip(":")
        else:
            content_lines.append(line)
    flush_content()
    if not blocks:
        blocks.append(Paragraph("Instructor solution required.", styles["SolutionText"]))
    return blocks


def build_answer_key_pdf(paper: GeneratedPaper, institution: str = "MGM UNIVERSITY", teacher_name: str = "Teacher") -> bytes:
    del teacher_name
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=22 * mm, leftMargin=22 * mm, topMargin=16 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="OfficialUniversity", parent=styles["Title"], fontName="Times-Bold", alignment=TA_CENTER, fontSize=16, leading=19, spaceAfter=1, textColor=colors.black))
    styles.add(ParagraphStyle(name="OfficialAddress", parent=styles["Normal"], fontName="Times-Roman", alignment=TA_CENTER, fontSize=10, leading=12, spaceAfter=5))
    styles.add(ParagraphStyle(name="OfficialExam", parent=styles["Heading2"], fontName="Times-Bold", alignment=TA_CENTER, fontSize=12, leading=15, spaceBefore=2, spaceAfter=5))
    styles.add(ParagraphStyle(name="OfficialTitle", parent=styles["Heading2"], fontName="Times-Bold", alignment=TA_CENTER, fontSize=13, leading=16, spaceBefore=0, spaceAfter=7))
    styles.add(ParagraphStyle(name="OfficialMeta", parent=styles["BodyText"], fontName="Times-Roman", fontSize=10, leading=13))
    styles.add(ParagraphStyle(name="SolutionQuestion", parent=styles["BodyText"], fontName="Times-Roman", fontSize=10, leading=13, spaceBefore=7, spaceAfter=4, keepWithNext=True))
    styles.add(ParagraphStyle(name="SolutionText", parent=styles["BodyText"], fontName="Times-Roman", fontSize=9.5, leading=12, spaceAfter=4, splitLongWords=1))
    styles.add(ParagraphStyle(name="SolutionSubheading", parent=styles["BodyText"], fontName="Times-Roman", fontSize=9.5, leading=12, spaceBefore=5, spaceAfter=2, keepWithNext=True))
    styles.add(ParagraphStyle(name="CorrectOption", parent=styles["BodyText"], fontName="Times-Roman", fontSize=10, leading=14, spaceAfter=8))
    story = _official_header(paper, paper.university_name or institution, "ANSWER KEY & MODEL SOLUTIONS", styles)
    question_number = 1
    for question_type, group in _question_groups(paper):
        story.append(Paragraph(escape(SECTION_TITLES.get(question_type, "Questions")), ParagraphStyle(name=f"AnswerSection{question_number}", parent=styles["SolutionQuestion"], fontName="Times-Bold", keepWithNext=True)))
        for _, question in group:
            label = Paragraph(f"<b>Q.{question_number}.</b> {escape(clean_print_text(question.text))}", styles["SolutionQuestion"])
            if question.question_type == "MCQ":
                correct = _mcq_correct_option(question)
                if correct:
                    _, option_text = correct
                    answer = Paragraph(f"Correct Option: {correct[0]}. {escape(option_text)}", styles["CorrectOption"])
                else:
                    answer = Paragraph("Correct option is not recorded for this legacy question.", styles["CorrectOption"])
                story.append(KeepTogether([label, answer]))
            else:
                blocks = _solution_blocks(question.answer, styles)
                if blocks:
                    story.append(KeepTogether([label, blocks[0]]))
                    story.extend(blocks[1:])
                else:
                    story.append(label)
            question_number += 1
    decorator = _page_chrome(paper)
    document.build(story, onFirstPage=decorator, onLaterPages=decorator)
    return buffer.getvalue()