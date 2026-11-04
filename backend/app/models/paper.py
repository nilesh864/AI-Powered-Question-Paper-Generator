from datetime import datetime, timezone
import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator


_PRINT_METADATA_TAG = re.compile(
    r"\[(?:offline\s+template(?:\s*[·|-]\s*set\s+[A-Z])?|template|easy|medium|hard|generated(?:_by)?[^]]*)\]\s*",
    flags=re.IGNORECASE,
)


def clean_print_text(text: str) -> str:
    return _PRINT_METADATA_TAG.sub("", text).strip()


class Question(BaseModel):
    id: str
    text: str
    marks: int = Field(gt=0)
    unit: str = "Unit 1"
    difficulty: Literal["Easy", "Medium", "Hard"] = "Medium"
    bloom: str = "Understand"
    confidence: float = Field(default=0, ge=0, le=1)
    generated_by: Literal["gemini", "ollama", "offline_fallback"] = "gemini"
    answer: str = ""
    duplicate_score: float = Field(default=0, ge=0, le=1)
    question_type: Literal["MCQ", "Short Answer", "Long Answer", "Case Study"] = "Long Answer"
    options: list[str] = Field(default_factory=list)
    correct_option: Literal["A", "B", "C", "D"] | None = None


class QuestionSection(BaseModel):
    question_type: Literal["MCQ", "Short Answer", "Long Answer", "Case Study"]
    question_count: int = Field(ge=0, le=50)
    total_marks: int = Field(ge=0, le=300)


class DifficultyDistribution(BaseModel):
    easy: int = Field(default=0, ge=0, le=100)
    medium: int = Field(default=100, ge=0, le=100)
    hard: int = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def validate_total(self):
        if self.easy + self.medium + self.hard != 100:
            raise ValueError("Difficulty percentages must add up to 100%.")
        return self


def difficulty_counts_for(question_count: int, distribution: DifficultyDistribution) -> dict[str, int]:
    levels = ("easy", "medium", "hard")
    exact_counts = {level: question_count * getattr(distribution, level) / 100 for level in levels}
    counts = {level: int(exact_counts[level]) for level in levels}
    remaining = question_count - sum(counts.values())
    remainder_order = sorted(levels, key=lambda level: (-(exact_counts[level] - counts[level]), levels.index(level)))
    for level in remainder_order[:remaining]:
        counts[level] += 1
    return counts


class PaperRequest(BaseModel):
    subject: str = Field(min_length=2, max_length=120)
    university_name: str = Field(default="MGM UNIVERSITY", min_length=2, max_length=160)
    institution_address: str = Field(default="Aurangabad-431003", min_length=2, max_length=200)
    program_name: str = Field(default="", max_length=160)
    course_title: str = Field(default="", max_length=160)
    course_code: str = ""
    semester: str = Field(default="", max_length=80)
    exam_type: str = Field(default="First Term Exam A.Y. 2024-25", min_length=2, max_length=160)
    units: list[str] = Field(min_length=1)
    total_marks: int = Field(default=100, ge=10, le=300)
    duration_minutes: int = Field(default=180, ge=30, le=600)
    question_count: int = Field(default=10, ge=3, le=50)
    sets: int = Field(default=3, ge=1, le=3)
    difficulty_level: Literal["Easy", "Medium", "Hard", "Balanced"] = "Medium"
    difficulty_distribution: DifficultyDistribution | None = None
    provider: Literal["auto", "gemini", "ollama"] | None = None
    question_types: list[Literal["MCQ", "Short Answer", "Long Answer", "Case Study"]] = Field(default_factory=lambda: ["MCQ", "Short Answer", "Long Answer", "Case Study"], min_length=1)
    sections: list[QuestionSection] = Field(default_factory=list, max_length=4)
    instructions: list[str] = Field(default_factory=lambda: ["All questions are compulsory.", "Marks are indicated against each question.", "Illustrate your answers with neat sketches wherever necessary."])

    @model_validator(mode="after")
    def validate_blueprint(self):
        if self.difficulty_distribution is None:
            self.difficulty_distribution = {
                "Easy": DifficultyDistribution(easy=100, medium=0, hard=0),
                "Hard": DifficultyDistribution(easy=0, medium=0, hard=100),
                "Balanced": DifficultyDistribution(easy=34, medium=33, hard=33),
            }.get(self.difficulty_level, DifficultyDistribution())
        else:
            active_levels = [
                level
                for level, percentage in (
                    ("Easy", self.difficulty_distribution.easy),
                    ("Medium", self.difficulty_distribution.medium),
                    ("Hard", self.difficulty_distribution.hard),
                )
                if percentage == 100
            ]
            self.difficulty_level = active_levels[0] if active_levels else "Balanced"
        if not self.sections:
            return self
        if len({section.question_type for section in self.sections}) != len(self.sections):
            raise ValueError("Each question format may appear only once in the section blueprint.")
        if sum(section.question_count for section in self.sections) != self.question_count:
            raise ValueError("Section question counts must add up to question_count.")
        if sum(section.total_marks for section in self.sections) != self.total_marks:
            raise ValueError("Section marks must add up to total_marks.")
        if any(section.question_count > 0 and section.total_marks < section.question_count for section in self.sections):
            raise ValueError("Every question in a non-empty section must be worth at least one mark.")
        if any(section.question_count == 0 and section.total_marks > 0 for section in self.sections):
            raise ValueError("Sections with no questions cannot have marks allocated.")
        return self


class GeneratedPaper(BaseModel):
    id: str
    title: str
    subject: str
    university_name: str = Field(default="MGM UNIVERSITY", min_length=2, max_length=160)
    institution_address: str = Field(default="Aurangabad-431003", min_length=2, max_length=200)
    program_name: str = Field(default="", max_length=160)
    course_title: str = Field(default="", max_length=160)
    course_code: str = ""
    semester: str = Field(default="", max_length=80)
    exam_type: str = Field(default="First Term Exam A.Y. 2024-25", min_length=2, max_length=160)
    set_label: str
    difficulty_level: Literal["Easy", "Medium", "Hard", "Balanced"] = "Medium"
    difficulty_distribution: DifficultyDistribution = Field(default_factory=DifficultyDistribution)
    generated_by: Literal["gemini", "ollama", "offline_fallback"] = "gemini"
    total_marks: int
    duration_minutes: int
    instructions: list[str] = Field(default_factory=lambda: ["All questions are compulsory.", "Marks are indicated against each question.", "Illustrate your answers with neat sketches wherever necessary."])
    questions: list[Question]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentMetadata(BaseModel):
    id: str
    owner_id: str
    filename: str
    category: str
    status: str = "indexed"
    chunk_count: int = 0
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))