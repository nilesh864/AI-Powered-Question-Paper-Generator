import io
import unittest

import pymupdf
from docx import Document

from app.models.paper import GeneratedPaper
from app.services.pdf_generator import build_exam_docx, build_exam_pdf


def sample_paper():
    return GeneratedPaper.model_validate({
        "id": "paper-1",
        "title": "Calculus Examination",
        "subject": "Calculus",
        "university_name": "MGM UNIVERSITY",
        "institution_address": "Aurangabad-431003",
        "program_name": "B.Tech",
        "course_title": "Calculus I",
        "course_code": "MA101",
        "semester": "I",
        "exam_type": "First Term Exam A.Y. 2024-25",
        "set_label": "A",
        "total_marks": 10,
        "duration_minutes": 60,
        "questions": [{
            "id": "question-1",
            "text": "[Offline template · Set A] [Easy] Explain limits.",
            "marks": 10,
            "question_type": "MCQ",
            "options": ["[Template] Option one", "Option two"],
        }],
    })


class PaperExportTests(unittest.TestCase):
    def test_pdf_has_official_header_and_no_generator_markers(self):
        pdf = pymupdf.open(stream=build_exam_pdf(sample_paper()), filetype="pdf")
        page = pdf[0]
        text = page.get_text()

        for expected in (
            "MGM UNIVERSITY",
            "Aurangabad-431003",
            "First Term Exam A.Y. 2024-25",
            "Program:",
            "B.Tech",
            "Sem:",
            "Course:",
            "Calculus I",
            "MA101",
            "Marks:",
            "Time:",
            "Instructions to the students",
            "Q.1.",
            "Explain limits.",
            "Option one",
        ):
            self.assertIn(expected, text)
        for internal_marker in ("Offline template", "[Easy]", "[Template]", "Tracking", "CONFIDENTIAL"):
            self.assertNotIn(internal_marker, text)

        spans = [span for block in page.get_text("dict")["blocks"] for line in block.get("lines", []) for span in line["spans"]]
        question_text = next(span for span in spans if span["text"].strip() == "Explain limits.")
        self.assertIn("Times-Roman", question_text["font"])
        question_number = next(span for span in spans if span["text"] == "Q.1.")
        section_heading = next(span for span in spans if span["text"].startswith("A) Select"))
        self.assertIn("Times-Bold", question_number["font"])
        self.assertIn("Times-Bold", section_heading["font"])

    def test_docx_prints_question_body_regular_and_section_label_bold(self):
        document = Document(io.BytesIO(build_exam_docx(sample_paper())))
        all_text = "\n".join(paragraph.text for paragraph in document.paragraphs) + "\n" + "\n".join(
            cell.text for table in document.tables for row in table.rows for cell in row.cells
        )
        self.assertIn("MGM UNIVERSITY", all_text)
        self.assertIn("Aurangabad-431003", all_text)
        self.assertIn("Calculus I", all_text)
        self.assertIn("Instructions to the students", all_text)
        for internal_marker in ("Offline template", "[Easy]", "[Template]"):
            self.assertNotIn(internal_marker, all_text)

        question = next(paragraph for paragraph in document.paragraphs if "Explain limits." in paragraph.text)
        self.assertTrue(question.runs[0].bold)
        self.assertFalse(next(run for run in question.runs if "Explain limits." in run.text).bold)
        option = next(paragraph for paragraph in document.paragraphs if "Option one" in paragraph.text)
        self.assertFalse(any(run.bold for run in option.runs))


if __name__ == "__main__":
    unittest.main()