"""Heuristic Form 16 Part B extraction with pandas + pydantic models."""

from __future__ import annotations

import hashlib
import io
import re

import pandas as pd

from models import Form16Extract


PAN_RE = re.compile(r"\b([A-Z]{5}\d{4}[A-Z])\b", re.IGNORECASE)


def _money(val: object) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    cleaned = re.sub(r"[^\d.\-]", "", str(val))
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def _find_amount_after_labels(text: str, labels: list[str]) -> float | None:
    lower = text.lower()
    for label in labels:
        idx = lower.find(label.lower())
        if idx == -1:
            continue
        window = text[idx : idx + 400]
        nums = re.findall(r"[\d,]+\.?\d*", window)
        if nums:
            return _money(nums[-1])
    return None


def extract_text_from_pdf_bytes(data: bytes) -> tuple[str, str]:
    """Returns (concatenated text, sha256 hex)."""
    import pdfplumber

    h = hashlib.sha256(data).hexdigest()
    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            parts.append(t)
    return "\n".join(parts), h


def parse_form16_text(text: str, file_hash: str) -> Form16Extract:
    """Parse Form 16 text into a validated Pydantic model using pandas heuristics."""

    lines = text.splitlines()
    df = pd.DataFrame({"line": lines, "lower": [ln.lower() for ln in lines]})

    pans = PAN_RE.findall(text)
    pan = pans[0].upper() if pans else None

    gs = _find_amount_after_labels(
        text,
        ["gross salary", "gross total income", "total gross", "aggregate salary", "salary as per"],
    )
    tds = _find_amount_after_labels(
        text,
        ["total amount of tax deducted", "tds deducted", "tax deducted at source", "aggregate of tax deducted"],
    )
    c80 = _find_amount_after_labels(text, ["deduction under chapter vi", "80c", "section 80c", "eightyc"])

    warnings: list[str] = []
    if gs is None:
        warnings.append("Could not confidently locate gross salary; defaulting to 0.")
    if tds is None:
        warnings.append("Could not confidently locate TDS; defaulting to 0.")

    employee_name: str | None = None
    employer_name: str | None = None
    for line in lines[:80]:
        low = line.lower()
        if "employee" in low and ":" in line:
            employee_name = line.split(":", 1)[-1].strip()[:120]
        if "employer" in low and "tan" not in low and ":" in line:
            employer_name = line.split(":", 1)[-1].strip()[:120]

    return Form16Extract(
        pan=pan,
        employee_name=employee_name,
        employer_name=employer_name,
        gross_salary=gs or 0.0,
        tds_deducted=tds or 0.0,
        total_80c=min(c80 or 0.0, 150_000),
        raw_text_sample=text[:4000],
        parse_warnings=warnings,
        sha256=file_hash,
    )


def parse_form16_pdf(data: bytes) -> Form16Extract:
    text, h = extract_text_from_pdf_bytes(data)
    return parse_form16_text(text, h)


def ocr_pdf_page_images(data: bytes, max_pages: int = 3, dpi: int = 200) -> str:
    """Rasterize first pages with PyMuPDF and OCR — requires Tesseract on PATH."""
    import pytesseract
    from PIL import Image
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    chunks: list[str] = []
    try:
        n = min(max_pages, doc.page_count)
        for i in range(n):
            page = doc.load_page(i)
            pix = page.get_pixmap(dpi=dpi)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            chunks.append(pytesseract.image_to_string(img))
    finally:
        doc.close()
    return "\n".join(chunks)
