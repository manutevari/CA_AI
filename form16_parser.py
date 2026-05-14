"""Heuristic Form 16 Part B text extraction from PDF text / OCR dump."""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from typing import Any

import pdfplumber


PAN_RE = re.compile(
    r"\b([A-Z]{5}\d{4}[A-Z])\b",
    re.IGNORECASE,
)


def _money(s: str) -> float:
    cleaned = re.sub(r"[^\d.\-]", "", s)
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _find_amount_after_labels(text: str, labels: list[str]) -> float | None:
    lower = text.lower()
    for label in labels:
        idx = lower.find(label.lower())
        if idx == -1:
            continue
        window = text[idx : idx + 400]
        # Last rupee-like number in window often is amount
        nums = re.findall(r"[\d,]+\.?\d*", window)
        if nums:
            return _money(nums[-1])
    return None


@dataclass
class Form16Extract:
    pan: str | None = None
    employer_name: str | None = None
    employee_name: str | None = None
    gross_salary: float = 0.0
    tds_deducted: float = 0.0
    total_80c: float = 0.0
    raw_text_sample: str = ""
    parse_warnings: list[str] = field(default_factory=list)
    sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pan": self.pan,
            "employer_name": self.employer_name,
            "employee_name": self.employee_name,
            "gross_salary": self.gross_salary,
            "tds_deducted": self.tds_deducted,
            "total_80c": self.total_80c,
            "parse_warnings": self.parse_warnings,
            "sha256": self.sha256,
        }


def extract_text_from_pdf_bytes(data: bytes) -> tuple[str, str]:
    """Returns (concatenated text, sha256 hex)."""
    h = hashlib.sha256(data).hexdigest()
    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            parts.append(t)
    return "\n".join(parts), h


def parse_form16_text(text: str, file_hash: str) -> Form16Extract:
    out = Form16Extract(raw_text_sample=text[:4000], sha256=file_hash)

    pans = PAN_RE.findall(text)
    if pans:
        out.pan = pans[0].upper()

    gs = _find_amount_after_labels(
        text,
        [
            "gross salary",
            "gross total income",
            "total gross",
            "aggregate salary",
            "salary as per",
        ],
    )
    if gs is not None:
        out.gross_salary = gs
    else:
        out.parse_warnings.append("Could not confidently locate gross salary; defaulting to 0.")

    tds = _find_amount_after_labels(
        text,
        [
            "total amount of tax deducted",
            "tds deducted",
            "tax deducted at source",
            "aggregate of tax deducted",
        ],
    )
    if tds is not None:
        out.tds_deducted = tds

    c80 = _find_amount_after_labels(
        text,
        ["deduction under chapter vi", "80c", "section 80c", "eightyc"],
    )
    if c80 is not None:
        out.total_80c = min(c80, 150_000)

    # Names: very heuristic
    for line in text.splitlines()[:80]:
        if "employee" in line.lower() and ":" in line:
            out.employee_name = line.split(":", 1)[-1].strip()[:120]
        if "employer" in line.lower() and "tan" not in line.lower() and ":" in line:
            out.employer_name = line.split(":", 1)[-1].strip()[:120]

    return out


def parse_form16_pdf(data: bytes) -> Form16Extract:
    text, h = extract_text_from_pdf_bytes(data)
    return parse_form16_text(text, h)


def ocr_pdf_page_images(data: bytes, max_pages: int = 3) -> str:
    """Rasterize first pages with PyMuPDF and OCR — requires Tesseract on PATH."""
    import pytesseract
    from PIL import Image
    import fitz  # PyMuPDF

    doc = fitz.open(stream=data, filetype="pdf")
    chunks: list[str] = []
    try:
        n = min(max_pages, doc.page_count)
        for i in range(n):
            page = doc.load_page(i)
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            chunks.append(pytesseract.image_to_string(img))
    finally:
        doc.close()
    return "\n".join(chunks)
