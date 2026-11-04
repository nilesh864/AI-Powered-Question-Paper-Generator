import asyncio
import re
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import settings
from app.db.mongodb import collection
from app.models.paper import DifficultyDistribution, difficulty_counts_for
from app.services.ollama_service import OllamaUnavailable, generate_structured_output

_embeddings = None
_vector_stores: dict[str, object] = {}
_index_lock = asyncio.Lock()
FALLBACK_GEMINI_MODELS = ("gemini-3.8-flash", "gemini-1.5-flash-8b", "gemini-1.5-pro")
GEMINI_ATTEMPT_TIMEOUT_SECONDS = 15
GEMINI_RATE_LIMIT_MESSAGE = "Gemini API daily request quota reached. Please try again later or configure a paid API key."


class GeminiQuotaExceeded(RuntimeError):
    """Raised when all configured Gemini models are rate-limited."""


class GeminiModelsUnavailable(RuntimeError):
    """Raised when candidate models are unavailable or time out."""


def _is_rate_limit_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code is None:
        status_code = getattr(getattr(error, "response", None), "status_code", None)
    code = getattr(error, "code", None)
    return status_code == 429 or code == 429 or "resourceexhausted" in type(error).__name__.lower() or "429" in str(error)


def _is_model_unavailable_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code is None:
        status_code = getattr(getattr(error, "response", None), "status_code", None)
    code = getattr(error, "code", None)
    return status_code == 404 or code == 404 or "404" in str(error) or "not found for api version" in str(error).lower()


async def _invoke_with_model_fallback(prompt_messages, output_schema, temperature: float):
    from langchain_google_genai import ChatGoogleGenerativeAI

    primary_model = settings.gemini_model or "gemini-3.8-flash"
    model_names = list(dict.fromkeys([primary_model, *FALLBACK_GEMINI_MODELS]))
    last_rate_limit: Exception | None = None
    last_model_error: Exception | None = None
    rate_limited_models: set[str] = set()
    unavailable_models: set[str] = set()
    for model_name in model_names:
        try:
            model = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=settings.gemini_api_key,
                temperature=temperature,
            ).with_structured_output(output_schema)
            return await asyncio.wait_for(
                model.ainvoke(prompt_messages),
                timeout=GEMINI_ATTEMPT_TIMEOUT_SECONDS,
            )
        except Exception as error:
            if _is_rate_limit_error(error):
                last_rate_limit = error
                rate_limited_models.add(model_name)
                continue
            if _is_model_unavailable_error(error):
                last_model_error = error
                unavailable_models.add(model_name)
                continue
            if isinstance(error, TimeoutError):
                last_model_error = error
                unavailable_models.add(model_name)
                continue
            raise
    if len(rate_limited_models) == len(model_names):
        raise GeminiQuotaExceeded(GEMINI_RATE_LIMIT_MESSAGE) from last_rate_limit
    if rate_limited_models or unavailable_models:
        raise GeminiModelsUnavailable("No configured Gemini model completed the request.") from last_model_error or last_rate_limit
    raise GeminiModelsUnavailable("No configured Gemini model is available.")


class DraftQuestion(BaseModel):
    text: str
    answer: str
    question_type: Literal["MCQ", "Short Answer", "Long Answer", "Case Study"]
    difficulty: Literal["Easy", "Medium", "Hard"]
    options: list[str] = Field(default_factory=list)
    correct_option: Literal["A", "B", "C", "D"] | None = None


class DraftQuestionSet(BaseModel):
    questions: list[DraftQuestion]


class VectorIndexError(RuntimeError):
    """Raised when extracted document text cannot be indexed."""


def _fallback_topics(context: str, subject: str, units: list[str], count: int) -> list[str]:
    sentences = [re.sub(r"\s+", " ", sentence).strip(" .:-") for sentence in re.split(r"[.!?\n]+", context) if len(sentence.split()) >= 3]
    topics: list[str] = []
    for sentence in sentences:
        topic = " ".join(sentence.split()[:8])
        if topic and topic.casefold() not in {item.casefold() for item in topics}:
            topics.append(topic)
    base = [f"{unit} in {subject}" for unit in units] or [f"{subject} course concepts"]
    topics.extend(topic for topic in base if topic.casefold() not in {item.casefold() for item in topics})
    if not topics:
        topics = [f"{subject} foundations", f"applications of {subject}", f"analysis of {subject}"]
    while len(topics) < count:
        topics.append(f"{topics[len(topics) % len(topics)]} (aspect {len(topics) + 1})")
    return topics


def _offline_question_set(
    subject: str,
    units: list[str],
    requested_types: list[str],
    context: str,
    set_label: str = "A",
    difficulty_level: str = "Medium",
    difficulty_distribution: DifficultyDistribution | dict[str, int] | None = None,
) -> list[dict[str, str | list[str]]]:
    if difficulty_distribution is None:
        difficulty_distribution = {
            "Easy": DifficultyDistribution(easy=100, medium=0, hard=0),
            "Hard": DifficultyDistribution(easy=0, medium=0, hard=100),
            "Balanced": DifficultyDistribution(easy=34, medium=33, hard=33),
        }.get(difficulty_level, DifficultyDistribution())
    elif isinstance(difficulty_distribution, dict):
        difficulty_distribution = DifficultyDistribution.model_validate(difficulty_distribution)
    difficulty_counts = difficulty_counts_for(len(requested_types), difficulty_distribution)
    question_difficulties = [
        level.title()
        for level in ("easy", "medium", "hard")
        for _ in range(difficulty_counts[level])
    ]
    topics = _fallback_topics(context, subject, units, len(requested_types))
    context_excerpt = re.sub(r"\s+", " ", context).strip()[:280] or f"the core concepts of {subject}"
    templates = {
        "MCQ": [
            "Which statement best explains {topic}?",
            "Which option correctly applies {topic} to a new example?",
            "What is the most accurate interpretation of {topic}?",
            "Which claim about {topic} is supported by the supplied course context?",
        ],
        "Short Answer": [
            "Define {topic} and give one relevant example.",
            "Briefly explain why {topic} matters in {subject}.",
            "State one key principle of {topic} and describe its effect.",
            "Summarize how {topic} relates to {unit}.",
        ],
        "Long Answer": [
            "Discuss {topic}, explaining its key principles and supporting your answer with course evidence.",
            "Compare the main aspects of {topic} and evaluate their significance in {subject}.",
            "Analyze the relationships involved in {topic} and develop a reasoned conclusion.",
            "Explain {topic} in depth, including its applications, limitations, and implications.",
        ],
        "Case Study": [
            "Scenario: A practitioner encounters a problem involving {topic}. Analyze the issue and justify a response.",
            "Scenario: New evidence changes assumptions about {topic}. Evaluate the evidence and recommend next steps.",
            "Scenario: A community applies {topic} under resource constraints. Assess the trade-offs and propose a solution.",
            "Scenario: Two interventions address {topic} differently. Compare their likely outcomes and defend a choice.",
        ],
    }
    easy_suffixes = ["Use a direct explanation.", "Focus on recall and a clear example.", "Apply the definition to one familiar case."]
    medium_suffixes = ["Explain the reasoning behind your answer.", "Connect the concept to one related principle.", "Use evidence from the course context."]
    hard_suffixes = ["Use multi-step reasoning and evaluate competing interpretations.", "Synthesize evidence, consider limitations, and justify your conclusion.", "Analyze a non-obvious case and defend your recommendation."]
    suffixes_by_difficulty = {"Easy": easy_suffixes, "Medium": medium_suffixes, "Hard": hard_suffixes}
    questions: list[dict[str, str | list[str]]] = []
    set_number = max(ord(set_label[:1].upper() or "A") - ord("A"), 0)
    for index, question_type in enumerate(requested_types):
        difficulty = question_difficulties[index]
        suffixes = suffixes_by_difficulty[difficulty]
        topic = topics[(index + set_number) % len(topics)]
        template_pool = templates[question_type]
        template = template_pool[(index + set_number) % len(template_pool)]
        unit = units[(index + set_number) % len(units)] if units else f"{subject}"
        question_text = template.format(topic=topic, subject=subject, unit=unit)
        if question_type in {"Long Answer", "Case Study"}:
            question_text = f"{question_text} {suffixes[(index + set_number) % len(suffixes)]}"
        question_text = f"[Offline template · Set {set_label}] {question_text}"
        source_note = f"Offline template; verify using course material: {context_excerpt}"
        if question_type == "MCQ":
            text = question_text
            correct = f"A course-supported explanation of {topic}"
            distractors = [f"An unrelated claim about {topic}", f"A contradiction of the context on {topic}", f"An unsupported generalization about {topic}"]
            rotation = (index + set_number) % len(distractors)
            distractors = distractors[rotation:] + distractors[:rotation]
            options = [
                correct,
                *distractors,
            ]
            answer = f"Template answer: {correct}. Confirm the best answer against the course material. {source_note}"
        elif question_type == "Short Answer":
            text = question_text
            options = []
            answer = f"Template answer: Define {topic}, explain its relevance, and provide an accurate course-based example. {source_note}"
        elif question_type == "Long Answer":
            text = question_text
            options = []
            answer = f"Template answer outline: Define {topic}, explain relevant principles and relationships, then support the argument with evidence and a conclusion. {source_note}"
        else:
            text = question_text
            options = []
            answer = f"Template answer outline: Identify the issues in the scenario, apply {topic}, assess alternatives, and justify a response using course evidence. {source_note}"
        questions.append({
            "text": text,
            "answer": answer,
            "question_type": question_type,
            "difficulty": difficulty,
            "options": options,
            "correct_option": "A" if question_type == "MCQ" else None,
            "generated_by": "offline_fallback",
        })
    return questions


def _get_embeddings():
    global _embeddings
    if _embeddings is None:
        from langchain_huggingface import HuggingFaceEmbeddings

        _embeddings = HuggingFaceEmbeddings(model_name=settings.embedding_model, encode_kwargs={"normalize_embeddings": True})
    return _embeddings


def split_text(text: str) -> list[str]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150, add_start_index=True)
    return splitter.split_text(text)


def _owner_store_path(owner_id: str) -> Path:
    if not owner_id or Path(owner_id).name != owner_id or owner_id in {".", ".."}:
        raise VectorIndexError("Invalid owner identifier for vector storage.")
    return Path(settings.vector_store_path) / "owners" / owner_id


async def _load_owner_store(owner_id: str):
    if owner_id in _vector_stores:
        return _vector_stores[owner_id]
    store_path = _owner_store_path(owner_id)
    if not (store_path / "index.faiss").exists():
        return None
    from langchain_community.vectorstores import FAISS

    embeddings = await asyncio.to_thread(_get_embeddings)
    store = await asyncio.to_thread(FAISS.load_local, str(store_path), embeddings, allow_dangerous_deserialization=True)
    _vector_stores[owner_id] = store
    return store


async def index_document(document_id: str, text: str, metadata: dict[str, str]) -> int:
    try:
        owner_id = metadata.get("owner_id", "")
        store_path = _owner_store_path(owner_id)
        chunks = split_text(text)
        if not chunks:
            return 0
        from langchain_community.vectorstores import FAISS

        embeddings = await asyncio.to_thread(_get_embeddings)
        metadatas = [{**metadata, "document_id": document_id, "chunk_index": str(index)} for index in range(len(chunks))]
        searchable_chunks = [
            f"Subject: {metadata.get('subject', '')}\nUnit: {metadata.get('unit_label', '')}\n{chunk}".strip()
            for chunk in chunks
        ]
        async with _index_lock:
            store = await _load_owner_store(owner_id)
            if store is None:
                store_path.mkdir(parents=True, exist_ok=True)
                store = await asyncio.to_thread(FAISS.from_texts, searchable_chunks, embeddings, metadatas)
                _vector_stores[owner_id] = store
            else:
                await asyncio.to_thread(store.add_texts, searchable_chunks, metadatas)
            await asyncio.to_thread(store.save_local, str(store_path))
        return len(chunks)
    except Exception as error:
        raise VectorIndexError(f"Vector indexing failed: {error}") from error


async def retrieve_context(query: str, limit: int = 6, owner_id: str | None = None) -> str:
    if not owner_id:
        return ""
    store = None
    try:
        store = await _load_owner_store(owner_id)
    except Exception:
        store = None
    if store is not None:
        try:
            docs = await asyncio.to_thread(store.similarity_search, query, k=limit, filter={"owner_id": owner_id})
            if docs:
                return "\n\n".join(doc.page_content for doc in docs)
        except Exception:
            pass

    if owner_id:
        documents = await collection("documents").find({"owner_id": owner_id}).to_list(500)
        query_terms = set(re.findall(r"[a-z0-9]+", _expand_query_terms(query).lower()))
        ranked: list[tuple[float, str]] = []
        for document in documents:
            text = document.get("text", "")
            if not text:
                continue
            chunks = split_text(text) if len(text) > 1000 else [text]
            document_labels = " ".join((document.get("subject", ""), document.get("unit_label", ""), document.get("filename", "")))
            for chunk in chunks:
                terms = re.findall(r"[a-z0-9]+", f"{document_labels} {chunk}".lower())
                if not terms:
                    continue
                frequencies = Counter(terms)
                overlap = sum(frequencies[term] for term in query_terms if term in frequencies)
                score = overlap / max(len(query_terms), 1)
                ranked.append((score, chunk))
        ranked.sort(key=lambda item: item[0], reverse=True)
        selected = [chunk for score, chunk in ranked[:limit] if score > 0]
        return "\n\n".join(selected)
    return ""


def _expand_query_terms(query: str) -> str:
    normalized = re.sub(r"\b(unit|chapter|module|lesson|topic)\s*[-:]?\s*(\d+)\b", r"unit \2 chapter \2 module \2 lesson \2", query, flags=re.IGNORECASE)
    return f"{normalized} course subject syllabus concepts learning outcomes"


async def delete_document_index(document_id: str, owner_id: str) -> None:
    try:
        store = await _load_owner_store(owner_id)
    except Exception:
        return
    if store is None:
        return
    try:
        stored_docs = getattr(store.docstore, "_dict", {})
        ids = [key for key, document in stored_docs.items() if document.metadata.get("document_id") == document_id]
        if ids:
            await asyncio.to_thread(store.delete, ids=ids)
            await asyncio.to_thread(store.save_local, str(_owner_store_path(owner_id)))
    except Exception:
        return


def _generated_items(response: DraftQuestionSet, generated_by: str) -> list[dict[str, str | list[str]]]:
    return [
        {
            "text": item.text.strip(),
            "answer": item.answer.strip(),
            "question_type": item.question_type,
            "difficulty": item.difficulty,
            "options": item.options,
            "correct_option": item.correct_option,
            "generated_by": generated_by,
        }
        for item in response.questions
        if item.text.strip() and item.answer.strip()
    ]


def _validate_generated_items(
    questions: list[dict[str, str | list[str]]],
    count: int,
    requested_types: list[str],
    difficulty_counts: dict[str, int],
) -> bool:
    actual_difficulty_counts = {
        level: sum(question.get("difficulty") == level.title() for question in questions)
        for level in ("easy", "medium", "hard")
    }
    return (
        len(questions) == count
        and len({str(question["text"]).casefold() for question in questions}) == count
        and all(question["question_type"] == requested_types[index] for index, question in enumerate(questions))
        and all(question["question_type"] != "MCQ" or len(question["options"]) == 4 for question in questions)
        and all(question["question_type"] != "MCQ" or question.get("correct_option") in {"A", "B", "C", "D"} for question in questions)
        and actual_difficulty_counts == difficulty_counts
    )


async def generate_question_set(
    subject: str,
    units: list[str],
    count: int,
    set_label: str,
    owner_id: str,
    question_types: list[str],
    sections: list[dict] | None = None,
    difficulty_level: str = "Medium",
    avoid_questions: list[str] | None = None,
    provider: str | None = None,
    difficulty_distribution: DifficultyDistribution | dict[str, int] | None = None,
) -> list[dict[str, str | list[str]]]:
    unit_aliases = ", ".join(f"{unit} (unit/chapter/module/lesson)" for unit in units)
    query = _expand_query_terms(f"{subject}: syllabus concepts and examination questions for {unit_aliases}")
    context = await retrieve_context(query, owner_id=owner_id)
    requested_types = [
        section["question_type"]
        for section in sections or []
        for _ in range(section["question_count"])
    ] or [question_types[index % len(question_types)] for index in range(count)]
    if difficulty_distribution is None:
        difficulty_distribution = {
            "Easy": DifficultyDistribution(easy=100, medium=0, hard=0),
            "Hard": DifficultyDistribution(easy=0, medium=0, hard=100),
            "Balanced": DifficultyDistribution(easy=34, medium=33, hard=33),
        }.get(difficulty_level, DifficultyDistribution())
    elif isinstance(difficulty_distribution, dict):
        difficulty_distribution = DifficultyDistribution.model_validate(difficulty_distribution)
    difficulty_counts = difficulty_counts_for(count, difficulty_distribution)
    section_brief = "\n".join(
        f"- {section['question_type']}: exactly {section['question_count']} questions, {section['total_marks']} marks total"
        for section in sections or []
    )
    difficulty_guidance = (
        "Easy questions test recall and direct application; Medium questions test understanding and analysis; "
        "Hard questions require multi-step reasoning, evaluation, or synthesis."
    )
    excluded_questions = "\n".join(f"- {text}" for text in (avoid_questions or [])[-60:])
    prompt = (
        f"Create exactly {count} original questions for university exam Set {set_label} in {subject}. "
        f"Use these question types in this exact order: {requested_types}. "
        f"Difficulty counts: exactly {difficulty_counts['easy']} Easy questions, {difficulty_counts['medium']} Medium questions, "
        f"and {difficulty_counts['hard']} Hard questions. Tag every question with its difficulty. {difficulty_guidance}\n"
        f"Section counts and mark allocations:\n{section_brief}\n"
        "Every generated question within a set MUST have a unique topic, concept stem, and wording. Do NOT repeat question formats or stems. "
        "When generating multiple paper sets (Set A, Set B, etc.), generate distinct questions or rephrased variants with altered options/scenarios for each set. Set A and Set B must NOT be identical. "
        "Do not reuse or closely paraphrase any excluded question below.\n"
        f"Previously used questions (avoid these):\n{excluded_questions}\n"
        "Use the selected unit context and produce accurate teacher-grade model solutions, not answer summaries. "
        "For MCQ, provide exactly four options and set correct_option to the letter A, B, C, or D; answer may include a brief rationale. "
        "For Short Answer, write a comprehensive 10-15 rendered lines covering definition, key components, and technical explanation. "
        "For Long Answer, write 25-30 rendered lines with these bold-markup subheadings: Introduction, Core Working Principles, Mathematical/Architectural Formulae (when applicable), Key Advantages, and Summary. "
        "For Case Study, write 50-70 rendered lines under bold-markup headings: Problem Statement & Context Analysis, Identification of Core Challenges, Step-by-Step Architectural / Technical Solution, Implementation & Strategy Breakdown, and Expected Outcomes & Summary Conclusion. "
        "Keep each solution academically accurate and specific to the supplied context. Use one concise factual answer for MCQ only. "
        "Non-MCQ questions must have an empty options list. Do not copy source text verbatim. Return all fields required by the JSON schema.\n\n"
        f"Selected units: {', '.join(units)}\nRetrieved context:\n{context}"
    )
    selected_provider = (provider or settings.llm_provider_mode).lower()
    if selected_provider not in {"auto", "gemini", "ollama"}:
        raise ValueError("Provider must be auto, gemini, or ollama.")

    async def try_gemini() -> list[dict[str, str | list[str]]]:
        if not settings.gemini_api_key:
            raise GeminiModelsUnavailable("GEMINI_API_KEY is not configured.")
        from langchain_core.messages import HumanMessage, SystemMessage

        response = await _invoke_with_model_fallback([
            SystemMessage(content="You create original, syllabus-grounded university assessments and worked answer keys."),
            HumanMessage(content=prompt),
        ], DraftQuestionSet, 0.45)
        result = _generated_items(response, "gemini")
        if not _validate_generated_items(result, count, requested_types, difficulty_counts):
            raise RuntimeError("Gemini returned questions that do not match the requested blueprint.")
        return result

    async def try_ollama() -> list[dict[str, str | list[str]]]:
        response = await generate_structured_output(prompt, DraftQuestionSet, temperature=0.45)
        result = _generated_items(response, "ollama")
        if not _validate_generated_items(result, count, requested_types, difficulty_counts):
            raise OllamaUnavailable("Ollama returned questions that do not match the requested blueprint.")
        return result

    if selected_provider == "gemini":
        return await try_gemini()
    if selected_provider == "ollama":
        try:
            return await try_ollama()
        except OllamaUnavailable:
            return _offline_question_set(subject, units, requested_types, context, set_label, difficulty_level, difficulty_distribution)

    if settings.gemini_api_key:
        try:
            return await try_gemini()
        except Exception:
            pass
    try:
        return await try_ollama()
    except Exception:
        return _offline_question_set(subject, units, requested_types, context, set_label, difficulty_level, difficulty_distribution)


async def regenerate_question(subject: str, unit: str, existing_question: str, owner_id: str) -> dict[str, str | list[str]]:
    context = await retrieve_context(f"{subject} {unit}: {existing_question}", owner_id=owner_id)
    if not settings.gemini_api_key:
        return _offline_question_set(subject, [unit], ["Long Answer"], context)[0]
    if not context.strip():
        raise RuntimeError("No indexed material matched this unit. Upload and index course documents first.")
    from langchain_core.messages import HumanMessage, SystemMessage

    prompt = (
        f"Create one new long-answer question and a teacher-grade model solution for {subject}, unit {unit}. "
        "Write 25-30 rendered lines under bold-markup subheadings: Introduction, Core Working Principles, "
        "Mathematical/Architectural Formulae (when applicable), Key Advantages, and Summary. "
        f"Do not repeat or paraphrase this question: {existing_question}. Use only this retrieved context:\n{context}"
    )
    try:
        response = await _invoke_with_model_fallback([
            SystemMessage(content="You write precise, syllabus-grounded questions and worked answer keys."),
            HumanMessage(content=prompt),
        ], DraftQuestion, 0.55)
    except (GeminiQuotaExceeded, GeminiModelsUnavailable):
        return _offline_question_set(subject, [unit], ["Long Answer"], context)[0]
    if response.text.strip() and response.answer.strip():
        return {"text": response.text.strip(), "answer": response.answer.strip(), "generated_by": "gemini"}
    raise RuntimeError("Gemini returned an empty regenerated question or answer.")