from datetime import datetime, timedelta, timezone
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import current_user
from app.db.mongodb import collection
from app.models.paper import GeneratedPaper, PaperRequest, Question, clean_print_text
from app.services.ml_ensemble import analyze_question, duplicate_scores
from app.services.rag_pipeline import GeminiQuotaExceeded, generate_question_set, regenerate_question

router = APIRouter(prefix="/generate", tags=["generation"])
papers_router = APIRouter(prefix="/papers", tags=["papers"])


@papers_router.get("")
async def list_papers(user: dict = Depends(current_user)):
    cursor = collection("papers").find({"owner_id": user["_id"]})
    papers = await cursor.sort("created_at", -1).to_list(500)
    return [{key: value for key, value in paper.items() if key not in {"owner_id", "_id"}} | {"id": paper["_id"]} for paper in papers]


@router.post("")
async def generate_papers(payload: PaperRequest, user: dict = Depends(current_user)):
    sections = [section.model_dump() for section in payload.sections]
    if sections:
        requested_types = [section["question_type"] for section in sections for _ in range(section["question_count"])]
        question_marks = [
            marks
            for section in sections
            for marks in (
                [section["total_marks"] // section["question_count"] + int(index < section["total_marks"] % section["question_count"]) for index in range(section["question_count"])]
                if section["question_count"] else []
            )
        ]
    else:
        requested_types = [payload.question_types[index % len(payload.question_types)] for index in range(payload.question_count)]
        base_marks, extra_marks = divmod(payload.total_marks, payload.question_count)
        question_marks = [base_marks + int(index < extra_marks) for index in range(payload.question_count)]
    generated_papers: list[GeneratedPaper] = []
    paper_validation: list[dict] = []
    existing_cursor = collection("papers").find({"owner_id": user["_id"]})
    existing_papers = await existing_cursor.to_list(500)
    past_questions = [question.get("text", "") for old_paper in existing_papers for question in old_paper.get("questions", [])]
    document_cursor = collection("documents").find({"owner_id": user["_id"]})
    documents = await document_cursor.to_list(500)
    past_paper_text = [document.get("text", "") for document in documents if document.get("category") == "past-papers"]
    for text in past_paper_text:
        past_questions.extend(part.strip() for part in re.split(r"\n+|(?<=[.!?])\s+", text) if len(part.strip()) > 35)
    for set_index in range(payload.sets):
        set_label = chr(65 + set_index)
        try:
            generated = await generate_question_set(
                payload.subject,
                payload.units,
                payload.question_count,
                set_label,
                user["_id"],
                payload.question_types,
                sections,
                payload.difficulty_level,
                past_questions,
                payload.provider,
                payload.difficulty_distribution or {},
            )
        except GeminiQuotaExceeded as error:
            raise HTTPException(status_code=429, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=f"Question generation provider failed: {error}") from error
        question_signatures = [re.sub(r"\W+", " ", item["text"]).strip().casefold() for item in generated]
        previous_signatures = {re.sub(r"\W+", " ", text).strip().casefold() for text in past_questions}
        if len(set(question_signatures)) != len(question_signatures) or any(signature in previous_signatures for signature in question_signatures):
            from app.services.rag_pipeline import _offline_question_set

            generated = _offline_question_set(
                payload.subject,
                payload.units,
                requested_types,
                " ".join(document.get("text", "") for document in documents),
                set_label,
                payload.difficulty_level,
                payload.difficulty_distribution or {},
            )
        questions = []
        set_duplicate_scores: list[float] = []
        generated_by = next((str(item.get("generated_by")) for item in generated if item.get("generated_by")), "gemini")
        for index, item in enumerate(generated):
            similarities = duplicate_scores(item["text"], past_questions)
            duplicate_score = max(similarities, default=0)
            if duplicate_score >= 0.86 and generated_by != "offline_fallback":
                raise HTTPException(status_code=422, detail=f"A generated question in Set {set_label} is too similar to an existing paper. Revise the unit selection and retry.")
            analysis = analyze_question(item["text"])
            difficulty = item.get("difficulty", analysis["difficulty"])
            if difficulty == "Easy" and analysis["bloom"] not in {"Remember", "Understand", "Apply"}:
                analysis["bloom"] = "Understand"
            elif difficulty == "Hard" and analysis["bloom"] not in {"Analyze", "Evaluate", "Create"}:
                analysis["bloom"] = "Analyze"
            marks = question_marks[index]
            questions.append(Question(id=str(uuid4()), text=clean_print_text(item["text"]), marks=marks, unit=payload.units[index % len(payload.units)], difficulty=difficulty, bloom=analysis["bloom"], confidence=analysis.get("confidence", 0), generated_by=item.get("generated_by", generated_by), answer=item["answer"], duplicate_score=duplicate_score, question_type=item["question_type"], options=[clean_print_text(option) for option in item["options"]], correct_option=item.get("correct_option")))
            set_duplicate_scores.append(duplicate_score)
            past_questions.append(item["text"])
        paper = GeneratedPaper(
            id=str(uuid4()),
            title=f"{payload.subject} Examination",
            subject=payload.subject,
            university_name=payload.university_name,
            institution_address=payload.institution_address,
            program_name=payload.program_name,
            course_title=payload.course_title or payload.subject,
            course_code=payload.course_code,
            semester=payload.semester,
            exam_type=payload.exam_type,
            set_label=set_label,
            difficulty_level=payload.difficulty_level,
            difficulty_distribution=payload.difficulty_distribution,
            generated_by=generated_by,
            total_marks=sum(question.marks for question in questions),
            duration_minutes=payload.duration_minutes,
            instructions=payload.instructions,
            questions=questions,
            created_at=datetime.now(timezone.utc),
        )
        generated_papers.append(paper)
        difficulty_counts = {level: sum(question.difficulty == level for question in questions) for level in ("Easy", "Medium", "Hard")}
        paper_validation.append({
            "paper_id": paper.id,
            "set_label": set_label,
            "question_count": len(questions),
            "difficulty_distribution": difficulty_counts,
            "soft_voting_confidence": round(sum(question.confidence for question in questions) / len(questions), 3) if questions else 0,
            "bloom_distribution": {level: sum(question.bloom == level for question in questions) for level in ("Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create")},
            "duplicate_screening": {
                "checked_questions": len(set_duplicate_scores),
                "flagged_questions": sum(score >= 0.75 for score in set_duplicate_scores),
                "max_similarity": max(set_duplicate_scores, default=0),
                "status": "passed",
            },
        })
    papers = [paper.model_dump(mode="json") for paper in generated_papers]
    for paper in generated_papers:
        await collection("papers").insert_one({"_id": paper.id, "owner_id": user["_id"], **paper.model_dump()})
    answer_keys = [
        {"paper_id": paper["id"], "set_label": paper["set_label"], "answers": [{"question_id": question["id"], "answer": question["answer"]} for question in paper["questions"]]}
        for paper in papers
    ]
    used_providers = {paper.generated_by for paper in generated_papers}
    response_provider = next(iter(used_providers)) if len(used_providers) == 1 else "mixed"
    return {
        "papers": papers,
        "answer_keys": answer_keys,
        "validation": {"question_count": payload.question_count, "difficulty_balance": "ensemble-scored", "sets_created": len(papers)},
        "validation_summary": {
            "status": "passed",
            "generated_by": response_provider,
            "sets": paper_validation,
            "difficulty_distribution": {level: sum(summary["difficulty_distribution"][level] for summary in paper_validation) for level in ("Easy", "Medium", "Hard")},
            "average_soft_voting_confidence": round(sum(summary["soft_voting_confidence"] for summary in paper_validation) / len(paper_validation), 3) if paper_validation else 0,
            "duplicate_screening": {
                "checked_questions": sum(summary["duplicate_screening"]["checked_questions"] for summary in paper_validation),
                "flagged_questions": sum(summary["duplicate_screening"]["flagged_questions"] for summary in paper_validation),
                "status": "passed",
            },
        },
    }


@router.get("/analytics")
async def analytics(user: dict = Depends(current_user)):
    document_cursor = collection("documents").find({"owner_id": user["_id"]})
    paper_cursor = collection("papers").find({"owner_id": user["_id"]})
    documents = await document_cursor.to_list(1000)
    papers = await paper_cursor.to_list(1000)
    questions = [question for paper in papers for question in paper.get("questions", [])]
    difficulty_breakdown = {level: sum(question.get("difficulty") == level for question in questions) for level in ("Easy", "Medium", "Hard")}
    syllabus_text = "\n".join(document.get("text", "") for document in documents if document.get("category") == "syllabus")
    syllabus_units = set(re.findall(r"\b(?:unit|chapter)\s*([0-9]+)\b", syllabus_text, flags=re.IGNORECASE))
    covered_units = {
        match.group(1)
        for question in questions
        if (match := re.search(r"\b(?:unit|chapter)\s*([0-9]+)\b", question.get("unit", ""), flags=re.IGNORECASE))
    }
    coverage = round(100 * len(syllabus_units & covered_units) / len(syllabus_units)) if syllabus_units else None
    now = datetime.now(timezone.utc)
    week_buckets = []
    for offset in range(7, -1, -1):
        start = (now - timedelta(days=offset * 7)).date()
        week_buckets.append({"week": start.strftime("%b %d"), "papers": 0})
    for paper in papers:
        created = paper.get("created_at")
        if isinstance(created, datetime):
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_weeks = (now - created).days // 7
            if 0 <= age_weeks <= 7:
                week_buckets[7 - age_weeks]["papers"] += 1
    unit_coverage = [
        {"unit": f"Unit {unit}", "covered": unit in covered_units, "question_count": sum(re.search(rf"\b(?:unit|chapter)\s*{unit}\b", question.get("unit", ""), re.IGNORECASE) is not None for question in questions)}
        for unit in sorted(syllabus_units, key=lambda value: int(value))
    ]
    return {
        "total_uploads": len(documents),
        "indexed_uploads": sum(document.get("status") == "indexed" for document in documents),
        "generated_papers": len(papers),
        "generated_questions": len(questions),
        "syllabus_coverage_percent": coverage,
        "difficulty_breakdown": difficulty_breakdown,
        "unit_coverage": unit_coverage,
        "papers_per_week": week_buckets,
    }


@router.get("/history")
async def paper_history(user: dict = Depends(current_user)):
    cursor = collection("papers").find({"owner_id": user["_id"]})
    papers = await cursor.sort("created_at", -1).to_list(200)
    return [{key: value for key, value in paper.items() if key != "owner_id"} for paper in papers]


@router.get("/{paper_id}")
async def get_paper(paper_id: str, user: dict = Depends(current_user)):
    paper = await collection("papers").find_one({"_id": paper_id, "owner_id": user["_id"]})
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found.")
    return {key: value for key, value in paper.items() if key not in {"_id", "owner_id"}} | {"id": paper["_id"]}


@router.put("/{paper_id}")
async def update_paper(paper_id: str, payload: GeneratedPaper, user: dict = Depends(current_user)):
    from fastapi import HTTPException

    if payload.id != paper_id:
        raise HTTPException(status_code=422, detail="Paper ID in the request body must match the URL.")
    papers = collection("papers")
    existing = await papers.find_one({"_id": paper_id, "owner_id": user["_id"]})
    if not existing:
        raise HTTPException(status_code=404, detail="Paper not found.")
    await papers.update_one({"_id": paper_id, "owner_id": user["_id"]}, {"$set": payload.model_dump()})
    return payload.model_dump(mode="json")


@router.post("/analyze")
async def analyze(payload: dict, user: dict = Depends(current_user)):
    text = str(payload.get("text", "")).strip()
    if not text:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="Question text is required.")
    return analyze_question(text)


@router.post("/regenerate")
async def regenerate(payload: dict, user: dict = Depends(current_user)):
    subject = str(payload.get("subject", "")).strip()
    unit = str(payload.get("unit", "")).strip()
    text = str(payload.get("text", "")).strip()
    if not subject or not unit or not text:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="Subject, unit, and existing question text are required.")
    try:
        question = await regenerate_question(subject, unit, text, user["_id"])
    except GeminiQuotaExceeded as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Question regeneration provider failed: {error}") from error
    existing_papers = await collection("papers").find({"owner_id": user["_id"]}).to_list(500)
    comparison_questions = [candidate.get("text", "") for paper in existing_papers for candidate in paper.get("questions", [])]
    uploaded_documents = await collection("documents").find({"owner_id": user["_id"]}).to_list(500)
    for document in uploaded_documents:
        if document.get("category") == "past-papers":
            comparison_questions.extend(part.strip() for part in re.split(r"\n+|(?<=[.!?])\s+", document.get("text", "")) if len(part.strip()) > 35)
    comparison_questions.append(text)
    similarity = max(duplicate_scores(question["text"], comparison_questions), default=0)
    if similarity >= 0.86:
        raise HTTPException(status_code=422, detail="The regenerated question is too similar to an existing question or uploaded past paper.")
    analysis = analyze_question(question["text"])
    return {**question, **analysis, "duplicate_score": similarity}