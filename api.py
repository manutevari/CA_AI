"""Minimal FastAPI layer — pipeline-powered PDF parse + tax computation."""

from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from pipeline import TaxPipeline

app = FastAPI(title="ITR Filing Automator API", version="0.2.0")


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
        pipeline = TaxPipeline()
        result = pipeline.run(data)
        if result.errors:
            raise HTTPException(status_code=422, detail="; ".join(result.errors))
        return JSONResponse(result.to_report())
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
