from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.api.auth import current_user
from app.core.config import settings
from app.db.mongodb import collection
from app.models.paper import GeneratedPaper
from app.services.pdf_generator import build_answer_key_pdf, build_exam_docx, build_exam_pdf

router = APIRouter(prefix="/export", tags=["export"])


async def _export_paper(paper_id: str, kind: str, user: dict):
    if kind not in {"paper", "paper-docx", "answer-key"}:
        raise HTTPException(status_code=404, detail="Export type not found.")
    record = await collection("papers").find_one({"_id": paper_id, "owner_id": user["_id"]})
    if not record:
        raise HTTPException(status_code=404, detail="Paper not found.")
    paper = GeneratedPaper.model_validate(record)
    if kind == "paper":
        content = build_exam_pdf(paper, settings.university_name, user.get("name", "Teacher"))
        media_type = "application/pdf"
        extension = "pdf"
    elif kind == "paper-docx":
        content = build_exam_docx(paper)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        extension = "docx"
    else:
        content = build_answer_key_pdf(paper, settings.university_name, user.get("name", "Teacher"))
        media_type = "application/pdf"
        extension = "pdf"
    filename = f"{paper.subject.replace(' ', '-')}-set-{paper.set_label}-{kind}.{extension}"
    return Response(content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "private, no-store", "Pragma": "no-cache", "X-Content-Type-Options": "nosniff"})


@router.get("/pdf/{paper_id}")
async def export_paper_pdf(paper_id: str, kind: str = "paper", user: dict = Depends(current_user)):
    return await _export_paper(paper_id, kind, user)


@router.get("/{paper_id}/{kind}")
async def export_paper(paper_id: str, kind: str, user: dict = Depends(current_user)):
    return await _export_paper(paper_id, kind, user)