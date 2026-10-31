"""Launch with: uvicorn app:app --host 127.0.0.1 --port 8000"""
from __future__ import annotations

import asyncio
import os
import re
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from summarizer import TransformerSummarizer, UserFacingError, extract_document

BASE = Path(__file__).resolve().parent
OUTPUT_DIR = BASE / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)
MAX_BYTES = 12 * 1024 * 1024
RETENTION_SECONDS = 60 * 60 * 4

app = FastAPI(title="PaperBrief AI", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
model = TransformerSummarizer()
model_slot = asyncio.Semaphore(1)


@app.exception_handler(UserFacingError)
async def user_error_handler(_request: Request, exc: UserFacingError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(BASE / "static" / "index.html")


def purge_expired_files():
    now = time.time()
    for path in OUTPUT_DIR.glob("*.txt"):
        if now - path.stat().st_mtime > RETENTION_SECONDS:
            try:
                path.unlink()
            except OSError:
                pass


def _summarize_data(data: bytes, ext: str):
    document = extract_document(data, ext)
    result = model.summarize(document.text)
    return document, result


@app.post("/api/summarize")
async def summarize(file: UploadFile = File(...)):
    filename = (file.filename or "").strip()
    ext = Path(filename).suffix.lower()
    if ext not in (".pdf", ".docx"):
        raise HTTPException(status_code=415, detail="Unsupported file. Upload a PDF (.pdf) or Word (.docx) document only. PPT, TXT and DOC are not accepted.")
    if file.content_type and file.content_type not in (
        "application/pdf", "application/x-pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream", "application/zip",
    ):
        raise HTTPException(status_code=415, detail="File type does not match a supported PDF or Word document.")
    data = await file.read(MAX_BYTES + 1)
    await file.close()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Maximum upload size is 12 MB.")
    # Avoid multiple concurrent generations exhausting GPU/CPU memory.
    if model_slot.locked():
        raise HTTPException(status_code=429, detail="The AI is summarizing another document. Please try again shortly.")
    async with model_slot:
        try:
            document, result = await run_in_threadpool(_summarize_data, data, ext)
        except UserFacingError:
            raise
        except Exception as exc:
            import logging
            logging.exception("Unexpected summarization failure")
            raise HTTPException(status_code=500, detail="An unexpected error occurred while summarizing. Please try another document.") from exc
    purge_expired_files()
    token = uuid.uuid4().hex
    safe_title = re.sub(r"[^A-Za-z0-9._ -]", "", Path(filename).stem).strip()[:80] or "Document"
    report = (
        f"RESEARCH DOCUMENT SUMMARY\n"
        f"Document: {safe_title}\n"
        f"Model: {result['model']}\n\n"
        f"OVERVIEW\n{result['summary']}\n\n"
        f"SECTION SUMMARIES\n"
        + "\n\n".join(f"Section {i}: {part}" for i, part in enumerate(result["sections"], 1))
        + "\n"
    )
    (OUTPUT_DIR / f"{token}.txt").write_text(report, encoding="utf-8")
    return {
        "id": token, "filename": filename, "summary": result["summary"],
        "sections": result["sections"], "chunks": result["chunks"],
        "model": result["model"], "download_url": f"/api/download/{token}",
    }


@app.get("/api/download/{token}")
async def download(token: str):
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise HTTPException(status_code=404, detail="Summary not found.")
    path = OUTPUT_DIR / f"{token}.txt"
    if not path.is_file() or time.time() - path.stat().st_mtime > RETENTION_SECONDS:
        raise HTTPException(status_code=404, detail="Summary expired or not found. Generate it again.")
    return FileResponse(path, media_type="text/plain; charset=utf-8", filename="research_summary.txt")
