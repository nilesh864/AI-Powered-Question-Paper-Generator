from datetime import datetime, timezone
import asyncio
import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.auth import current_user
from app.core.config import settings
from app.db.mongodb import collection
from app.services.document_parser import parse_document
from app.services.rag_pipeline import VectorIndexError, delete_document_index, index_document

router = APIRouter(prefix="/documents", tags=["documents"])
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_SUFFIXES = {".pdf", ".docx", ".pptx", ".txt", ".md"}
ALLOWED_CATEGORIES = {"syllabus", "lecture-notes", "ppt", "past-papers"}


@router.get("")
async def list_documents(user: dict = Depends(current_user)):
    cursor = collection("documents").find({"owner_id": user["_id"]})
    documents = await cursor.sort("uploaded_at", -1).to_list(500)
    return [{key: value for key, value in document.items() if key not in {"text", "_id", "storage_path"}} | {"id": document["_id"]} for document in documents]


@router.post("/upload", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form("lecture-notes"),
    subject: str = Form(""),
    unit_label: str = Form(""),
    user: dict = Depends(current_user),
):
    filename = Path(file.filename or "upload").name
    if Path(filename).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Upload a PDF, DOCX, PPTX, TXT, or Markdown file.")
    if category not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Category must be one of: {', '.join(sorted(ALLOWED_CATEGORIES))}.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 25 MB upload limit.")
    try:
        extraction = await parse_document(filename, content)
    except Exception as error:
        raise HTTPException(status_code=422, detail=f"Could not read document: {error}") from error
    if not extraction.text.strip():
        raise HTTPException(status_code=422, detail="No readable text was found in this file.")
    document_id = str(uuid4())
    upload_root = Path(settings.upload_dir).resolve()
    owner_dir = (upload_root / user["_id"]).resolve()
    try:
        owner_dir.relative_to(upload_root)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid owner storage path.") from error
    owner_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    stored_path = owner_dir / f"{document_id}{Path(filename).suffix.lower()}"
    await asyncio.to_thread(stored_path.write_bytes, content)
    if os.name != "nt":
        stored_path.chmod(0o600)
    try:
        chunk_count = await index_document(document_id, extraction.text, {
            "owner_id": user["_id"],
            "filename": filename,
            "category": category,
            "subject": subject.strip(),
            "unit_label": unit_label.strip(),
        })
    except VectorIndexError as error:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail=str(error)) from error
    if chunk_count == 0:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="The uploaded document contained no indexable text.")
    metadata = {"_id": document_id, "owner_id": user["_id"], "filename": filename, "category": category, "subject": subject.strip(), "unit_label": unit_label.strip(), "page_count": extraction.page_count, "extracted_characters": len(extraction.text), "status": "indexed", "chunk_count": chunk_count, "uploaded_at": datetime.now(timezone.utc), "text": extraction.text, "storage_path": str(stored_path)}
    try:
        await collection("documents").insert_one(metadata)
    except Exception:
        await delete_document_index(document_id, user["_id"])
        stored_path.unlink(missing_ok=True)
        raise
    return {**{key: value for key, value in metadata.items() if key not in {"text", "_id", "storage_path"}}, "id": document_id}


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: str, user: dict = Depends(current_user)):
    document = await collection("documents").find_one({"_id": document_id, "owner_id": user["_id"]})
    if document:
        await delete_document_index(document_id, user["_id"])
        await collection("documents").delete_one({"_id": document_id, "owner_id": user["_id"]})
        stored_path = document.get("storage_path")
        if stored_path:
            Path(stored_path).unlink(missing_ok=True)