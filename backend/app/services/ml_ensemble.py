import re
from collections.abc import Sequence

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier, GradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

FEATURE_NAMES = ("token_count", "flesch_reading_ease", "flesch_kincaid_grade", "syntax_depth", "lexical_diversity", "technical_density")
TECHNICAL_TERMS = {
    "algorithm", "analysis", "architecture", "calculate", "classify", "compare", "configure", "database",
    "derive", "design", "develop", "differentiate", "evaluate", "explain", "implement", "integration",
    "mechanism", "methodology", "optimization", "principle", "prove", "system", "theorem", "validate",
}
BLOOM_LEVELS = ("Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create")


def extract_features(text: str) -> list[float]:
    words = re.findall(r"[A-Za-z]+", text.lower())
    sentences = [sentence for sentence in re.split(r"[.!?]+", text) if sentence.strip()]
    syllables = sum(max(1, len(re.findall(r"[aeiouy]+", word))) for word in words)
    word_count = max(len(words), 1)
    sentence_count = max(len(sentences), 1)
    syllables_per_word = syllables / word_count
    words_per_sentence = word_count / sentence_count
    flesch = 206.835 - 1.015 * words_per_sentence - 84.6 * syllables_per_word
    grade_level = 0.39 * words_per_sentence + 11.8 * syllables_per_word - 15.59
    clauses = len(re.findall(r"\b(which|that|because|although|while|whereas|if|when)\b", text.lower()))
    syntax_depth = min(12, 1 + clauses + text.count(";") + text.count(":"))
    lexical_diversity = len(set(words)) / word_count
    density = sum(word in TECHNICAL_TERMS for word in words) / word_count
    return [float(word_count), float(np.clip(flesch, -30, 120)), float(np.clip(grade_level, -10, 30)), float(syntax_depth), float(lexical_diversity), float(density)]


def _training_data() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(73)
    difficulty_centers = {"Easy": [9, 88, 2, 1, 0.9, 0.02], "Medium": [20, 61, 8, 3, 0.78, 0.10], "Hard": [32, 38, 14, 6, 0.68, 0.20]}
    bloom_centers = np.array([
        [8, 84, 2, 1, 0.91, 0.02], [14, 72, 5, 2, 0.84, 0.05], [20, 62, 8, 3, 0.79, 0.11],
        [27, 49, 11, 5, 0.73, 0.15], [28, 43, 13, 6, 0.69, 0.20], [24, 52, 10, 5, 0.72, 0.18],
    ])
    difficulty_rows: list[np.ndarray] = []
    difficulty_labels: list[str] = []
    bloom_rows: list[np.ndarray] = []
    bloom_labels: list[str] = []
    for difficulty, center in difficulty_centers.items():
        for _ in range(90):
            difficulty_rows.append(np.array(center) + rng.normal(0, [5, 9, 2.5, 1.3, 0.08, 0.05]))
            difficulty_labels.append(difficulty)
    for index, level in enumerate(BLOOM_LEVELS):
        for _ in range(80):
            bloom_rows.append(bloom_centers[index] + rng.normal(0, [6, 10, 2.5, 1.4, 0.09, 0.06]))
            bloom_labels.append(level)
    return np.vstack(difficulty_rows), np.array(difficulty_labels), np.vstack(bloom_rows), np.array(bloom_labels)


def _classifier() -> VotingClassifier:
    return VotingClassifier(
        estimators=[
            ("forest", RandomForestClassifier(n_estimators=90, max_depth=8, random_state=41)),
            ("extra", ExtraTreesClassifier(n_estimators=90, max_depth=8, random_state=41)),
            ("boost", GradientBoostingClassifier(n_estimators=50, max_depth=2, random_state=41)),
        ],
        voting="soft",
    )


def _models() -> tuple[VotingClassifier, VotingClassifier]:
    difficulty_x, difficulty_y, bloom_x, bloom_y = _training_data()
    difficulty_model, bloom_model = _classifier(), _classifier()
    difficulty_model.fit(difficulty_x, difficulty_y)
    bloom_model.fit(bloom_x, bloom_y)
    return difficulty_model, bloom_model


DIFFICULTY_MODEL, BLOOM_MODEL = _models()


def analyze_question(text: str) -> dict[str, str | float]:
    features = np.array(extract_features(text), dtype=float).reshape(1, -1)
    return {
        "difficulty": str(DIFFICULTY_MODEL.predict(features)[0]),
        "bloom": str(BLOOM_MODEL.predict(features)[0]),
        "confidence": round(float(max(DIFFICULTY_MODEL.predict_proba(features)[0])), 3),
    }


def duplicate_scores(candidate: str, past_questions: Sequence[str]) -> list[float]:
    past_questions = [question for question in past_questions if question.strip()]
    if not candidate.strip() or not past_questions:
        return []
    try:
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
        matrix = vectorizer.fit_transform([candidate, *past_questions])
        return [round(float(score), 4) for score in cosine_similarity(matrix[0:1], matrix[1:]).ravel()]
    except ValueError:
        return [0.0 for _ in past_questions]