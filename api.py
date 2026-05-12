"""Minimal FastAPI layer for document upload + parse (optional alongside Streamlit)."""

from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from form16_parser import parse_form16_pdf

app = FastAPI(title="ITR Filing Automator API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/parse-form16")
async def parse_form16(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported.")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 15 MB).")
    try:
        parsed = parse_form16_pdf(data)
    except Exception as exc:  # noqa: BLE001 — surface parse errors
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(parsed.to_dict())
