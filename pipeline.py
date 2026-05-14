"""Node-based processing pipeline for TaxPilot AI.

Each node is a self-contained processing step (tool) that can be
chained into a full extraction → computation → export pipeline.
"""

from __future__ import annotations

import hashlib
import io
import re
import time
from abc import ABC, abstractmethod
from typing import Any

import numpy as np
import pandas as pd

from models import (
    Form16Extract,
    PipelineMetadata,
    PipelineResult,
    RegimeComparison,
    Regime,
    TaxInputs,
    TaxResult,
)


PAN_RE = re.compile(r"\b([A-Z]{5}\d{4}[A-Z])\b", re.IGNORECASE)


def _money(val: Any) -> float:
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


# ---------------------------------------------------------------------------
# Base node
# ---------------------------------------------------------------------------


class PipelineNode(ABC):
    name: str

    @abstractmethod
    def process(self, ctx: dict[str, Any]) -> dict[str, Any]:
        ...


# ---------------------------------------------------------------------------
# Node: PDF text extractor
# ---------------------------------------------------------------------------


class PDFExtractor(PipelineNode):
    name = "pdf_extractor"

    def process(self, ctx: dict[str, Any]) -> dict[str, Any]:
        data: bytes = ctx.get("pdf_bytes", b"")
        if not data:
            ctx["errors"] = ctx.get("errors", []) + ["No PDF bytes provided"]
            return ctx

        import pdfplumber

        h = hashlib.sha256(data).hexdigest()
        parts: list[str] = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                parts.append(t)
        text = "\n".join(parts)

        ctx["raw_text"] = text
        ctx["file_hash"] = h
        ctx["page_count"] = len(parts)
        return ctx


# ---------------------------------------------------------------------------
# Node: OCR enhancer (uses Tesseract)
# ---------------------------------------------------------------------------


class OCREnhancer(PipelineNode):
    name = "ocr_enhancer"

    def __init__(self, max_pages: int = 3, dpi: int = 200, force: bool = False):
        self.max_pages = max_pages
        self.dpi = dpi
        self.force = force

    def process(self, ctx: dict[str, Any]) -> dict[str, Any]:
        text: str = ctx.get("raw_text", "")
        data: bytes = ctx.get("pdf_bytes", b"")

        if not self.force and len(text.strip()) >= 50:
            return ctx

        try:
            import pytesseract
            from PIL import Image
            import fitz

            doc = fitz.open(stream=data, filetype="pdf")
            chunks: list[str] = []
            try:
                n = min(self.max_pages, doc.page_count)
                for i in range(n):
                    page = doc.load_page(i)
                    pix = page.get_pixmap(dpi=self.dpi)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    chunks.append(pytesseract.image_to_string(img))
            finally:
                doc.close()

            ocr_text = "\n".join(chunks)
            if len(ocr_text.strip()) > len(text.strip()):
                ctx["raw_text"] = ocr_text
                ctx["ocr_applied"] = True
        except ImportError:
            ctx.setdefault("warnings", []).append("pytesseract/PIL not installed; OCR skipped")
        except Exception as e:
            ctx.setdefault("warnings", []).append(f"OCR failed: {e}")

        return ctx


# ---------------------------------------------------------------------------
# Node: Form 16 parser (pandas-based structured extraction)
# ---------------------------------------------------------------------------


class Form16Parser(PipelineNode):
    name = "form16_parser"

    AMOUNT_LABELS: dict[str, list[str]] = {
        "gross_salary": [
            "gross salary", "gross total income", "total gross",
            "aggregate salary", "salary as per",
        ],
        "tds_deducted": [
            "total amount of tax deducted", "tds deducted",
            "tax deducted at source", "aggregate of tax deducted",
        ],
        "total_80c": [
            "deduction under chapter vi", "80c", "section 80c", "eightyc",
        ],
    }

    def process(self, ctx: dict[str, Any]) -> dict[str, Any]:
        text: str = ctx.get("raw_text", "")
        file_hash: str = ctx.get("file_hash", "")
        warnings: list[str] = ctx.get("warnings", [])

        lines = text.splitlines()
        df = pd.DataFrame({"line": lines})
        df["lower"] = df["line"].str.lower()
        df["len"] = df["line"].str.len()

        pans = PAN_RE.findall(text)
        pan = pans[0].upper() if pans else None

        extracted: dict[str, float | None] = {}
        for field, labels in self.AMOUNT_LABELS.items():
            val = _find_amount_after_labels(text, labels)
            if val is not None:
                extracted[field] = val
            else:
                extracted[field] = None
                warnings.append(f"Could not locate {field}; defaulting to 0.")

        gross = extracted.get("gross_salary") or 0.0
        tds = extracted.get("tds_deducted") or 0.0
        c80 = min(extracted.get("total_80c") or 0.0, 150_000)

        employee_name: str | None = None
        employer_name: str | None = None
        for line in lines[:80]:
            low = line.lower()
            if "employee" in low and ":" in line:
                employee_name = line.split(":", 1)[-1].strip()[:120]
            if "employer" in low and "tan" not in low and ":" in line:
                employer_name = line.split(":", 1)[-1].strip()[:120]

        form16 = Form16Extract(
            pan=pan,
            employee_name=employee_name,
            employer_name=employer_name,
            gross_salary=gross,
            tds_deducted=tds,
            total_80c=c80,
            raw_text_sample=text[:4000],
            parse_warnings=[w for w in warnings if "Could not locate" in w],
            sha256=file_hash,
        )

        ctx["form16"] = form16
        ctx["warnings"] = warnings
        ctx["parsed_lines"] = len(lines)
        return ctx


# ---------------------------------------------------------------------------
# Node: Tax calculator (numpy-accelerated)
# ---------------------------------------------------------------------------


class TaxCalculator(PipelineNode):
    name = "tax_calculator"

    # New regime brackets: (limit, rate) — progressive
    NEW_BRACKETS: list[tuple[float, float]] = [
        (300_000, 0.00),
        (400_000, 0.05),
        (300_000, 0.10),
        (200_000, 0.15),
        (300_000, 0.20),
    ]
    NEW_CEILING_RATE = 0.30

    # Old regime slabs as cumulative breakpoints: (threshold, rate)
    OLD_BRACKETS: list[tuple[float, float]] = [
        (250_000, 0.00),
        (250_000, 0.05),
        (500_000, 0.20),
    ]
    OLD_CEILING_RATE = 0.30

    @staticmethod
    def _slab_tax_new(taxable: float) -> float:
        if taxable <= 0:
            return 0.0
        r = float(taxable)
        tax = 0.0
        for limit, rate in TaxCalculator.NEW_BRACKETS:
            chunk = min(r, limit)
            tax += chunk * rate
            r -= chunk
            if r <= 0:
                return round(tax, 2)
        tax += r * TaxCalculator.NEW_CEILING_RATE
        return round(tax, 2)

    @staticmethod
    def _slab_tax_old(taxable: float) -> float:
        if taxable <= 0:
            return 0.0
        r = float(taxable)
        tax = 0.0
        for limit, rate in TaxCalculator.OLD_BRACKETS:
            chunk = min(r, limit)
            tax += chunk * rate
            r -= chunk
            if r <= 0:
                return round(tax, 2)
        tax += r * TaxCalculator.OLD_CEILING_RATE
        return round(tax, 2)

    @staticmethod
    def _rebate_87a_old(income: float, tax_before: float) -> float:
        return min(tax_before, 12_500) if income <= 500_000 else 0.0

    @staticmethod
    def _rebate_87a_new(income: float, tax_before: float) -> float:
        return min(tax_before, 25_000) if income <= 700_000 else 0.0

    @staticmethod
    def _cess(amount: float) -> float:
        return round(amount * 0.04, 2)

    def _compute(self, inputs: TaxInputs, regime: Regime, tds_paid: float) -> TaxResult:
        gross_total = max(0.0, inputs.gross_total)

        if regime == "new":
            std = max(inputs.standard_deduction, 75_000)
            taxable = max(0.0, round(gross_total - std, 2))
            tax_before = self._slab_tax_new(taxable)
            rebate = self._rebate_87a_new(taxable, tax_before)
        else:
            std = max(inputs.standard_deduction, 50_000)
            deductions = min(inputs.chapter_via, 150_000)
            taxable = max(0.0, round(gross_total - std - deductions - inputs.hra_exemption, 2))
            tax_before = self._slab_tax_old(taxable)
            rebate = self._rebate_87a_old(taxable, tax_before)

        tax_after = max(0.0, round(tax_before - rebate, 2))
        cess = self._cess(tax_after)
        total = round(tax_after + cess, 2)

        return TaxResult(
            regime=regime,
            gross_total=round(gross_total, 2),
            taxable_income=taxable,
            tax_before_cess=tax_before,
            rebate_87a=rebate,
            tax_after_rebate=tax_after,
            cess=cess,
            total_tax=total,
            tds_credit=round(tds_paid, 2),
            refund_or_payable=round(tds_paid - total, 2),
        )

    def process(self, ctx: dict[str, Any]) -> dict[str, Any]:
        form16: Form16Extract | None = ctx.get("form16")
        if not form16:
            ctx["errors"] = ctx.get("errors", []) + ["No Form16 data for tax calculation"]
            return ctx

        other_income = ctx.get("other_income", 0.0)
        hra_exemption = ctx.get("hra_exemption", 0.0)
        chapter_via_manual = ctx.get("chapter_via_manual")

        inputs = TaxInputs(
            gross_salary=form16.gross_salary,
            standard_deduction=0.0,
            chapter_via=chapter_via_manual if chapter_via_manual is not None else form16.total_80c,
            hra_exemption=hra_exemption,
            other_income=other_income,
        )

        new_r = self._compute(inputs, "new", form16.tds_deducted)
        old_r = self._compute(inputs, "old", form16.tds_deducted)
        recommended: Regime = "new" if new_r.total_tax <= old_r.total_tax else "old"

        ctx["tax_comparison"] = RegimeComparison(
            new_regime=new_r,
            old_regime=old_r,
            recommended=recommended,
        )
        return ctx


# ---------------------------------------------------------------------------
# Node: XML export
# ---------------------------------------------------------------------------


class XMLExportNode(PipelineNode):
    name = "xml_export"

    def process(self, ctx: dict[str, Any]) -> dict[str, Any]:
        import xml.etree.ElementTree as ET
        from xml.dom import minidom

        form16: Form16Extract | None = ctx.get("form16")
        comparison: RegimeComparison | None = ctx.get("tax_comparison")
        if not form16 or not comparison:
            return ctx

        chosen = comparison.new_regime if comparison.recommended == "new" else comparison.old_regime

        root = ET.Element(
            "ITRReturn",
            {
                "xmlns": "https://incometaxindia.gov.in/demo/mvp",
                "Form": "ITR-1",
                "AssessmentYear": ctx.get("assessment_year", "2025-26"),
            },
        )
        ET.SubElement(root, "PAN").text = form16.pan or ""
        ET.SubElement(root, "EmployeeName").text = form16.employee_name or ""
        ET.SubElement(root, "EmployerName").text = form16.employer_name or ""
        inc = ET.SubElement(root, "Income")
        ET.SubElement(inc, "Salary").text = f"{form16.gross_salary:.2f}"
        ET.SubElement(inc, "OtherIncome").text = f"{ctx.get('other_income', 0.0):.2f}"
        ded = ET.SubElement(root, "DeductionsChapterVIA")
        ET.SubElement(ded, "Total80C").text = f"{form16.total_80c:.2f}"
        tax = ET.SubElement(root, "TaxComputation", {"Regime": chosen.regime})
        ET.SubElement(tax, "TaxableIncome").text = f"{chosen.taxable_income:.2f}"
        ET.SubElement(tax, "TotalTax").text = f"{chosen.total_tax:.2f}"
        ET.SubElement(tax, "TDSCredit").text = f"{chosen.tds_credit:.2f}"
        ET.SubElement(tax, "RefundOrPayable").text = f"{chosen.refund_or_payable:.2f}"

        rough = ET.tostring(root, encoding="unicode")
        parsed = minidom.parseString(rough)
        ctx["demo_xml"] = parsed.toprettyxml(indent="  ")
        return ctx


# ---------------------------------------------------------------------------
# Node: PDF summary export
# ---------------------------------------------------------------------------


class PDFExportNode(PipelineNode):
    name = "pdf_export"

    def process(self, ctx: dict[str, Any]) -> dict[str, Any]:
        from datetime import datetime, timezone
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.pdfgen import canvas

        form16: Form16Extract | None = ctx.get("form16")
        comparison: RegimeComparison | None = ctx.get("tax_comparison")
        if not form16 or not comparison:
            return ctx

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        width, height = A4
        y = height - 2 * cm
        c.setFont("Helvetica-Bold", 14)
        c.drawString(2 * cm, y, "ITR Filing Automator — Summary (MVP / Demo)")
        y -= 0.8 * cm
        c.setFont("Helvetica", 9)
        c.drawString(
            2 * cm, y,
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} — Not for official filing.",
        )
        y -= 1.2 * cm

        def line(label: str, value: str, bold: bool = False) -> None:
            nonlocal y
            if y < 2 * cm:
                c.showPage()
                y = height - 2 * cm
            c.setFont("Helvetica-Bold" if bold else "Helvetica", 10 if bold else 9)
            c.drawString(2 * cm, y, f"{label}: {value}")
            y -= 0.45 * cm

        line("PAN (parsed)", form16.pan or "—")
        line("Employee", form16.employee_name or "—")
        line("Employer", form16.employer_name or "—")
        line("Gross salary (parsed)", f"₹ {form16.gross_salary:,.2f}", bold=True)
        line("TDS (parsed)", f"₹ {form16.tds_deducted:,.2f}")
        line("80C / Chapter VI-A (parsed)", f"₹ {form16.total_80c:,.2f}")
        y -= 0.3 * cm
        c.setFont("Helvetica-Bold", 11)
        c.drawString(2 * cm, y, "Tax computation")
        y -= 0.6 * cm

        def block(title: str, r: TaxResult) -> None:
            nonlocal y
            c.setFont("Helvetica-Bold", 10)
            c.drawString(2 * cm, y, title)
            y -= 0.5 * cm
            line("  Taxable income", f"₹ {r.taxable_income:,.2f}")
            line("  Tax before cess", f"₹ {r.tax_before_cess:,.2f}")
            line("  Rebate 87A", f"₹ {r.rebate_87a:,.2f}")
            line("  Cess (4%)", f"₹ {r.cess:,.2f}")
            line("  Total tax", f"₹ {r.total_tax:,.2f}", bold=True)
            line("  Refund / payable (vs TDS)", f"₹ {r.refund_or_payable:,.2f}", bold=True)
            y -= 0.4 * cm

        block("New regime (simplified FY 2024-25)", comparison.new_regime)
        block("Old regime (simplified FY 2024-25)", comparison.old_regime)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(2 * cm, y, f"Suggested regime (lower liability): {comparison.recommended}")
        y -= 0.8 * cm
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(2 * cm, y, "Disclaimer: Demo tool only. Verify with a qualified tax professional before filing.")
        c.showPage()
        c.save()
        buf.seek(0)

        ctx["summary_pdf"] = buf.read()
        return ctx


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------


class TaxPipeline:
    def __init__(self, nodes: list[PipelineNode] | None = None):
        self.nodes = nodes or [
            PDFExtractor(),
            OCREnhancer(),
            Form16Parser(),
            TaxCalculator(),
            XMLExportNode(),
            PDFExportNode(),
        ]

    def run(
        self,
        pdf_bytes: bytes,
        other_income: float = 0.0,
        hra_exemption: float = 0.0,
        chapter_via_manual: float | None = None,
        assessment_year: str = "2025-26",
        force_ocr: bool = False,
    ) -> PipelineResult:
        start = time.perf_counter()

        ctx: dict[str, Any] = {
            "pdf_bytes": pdf_bytes,
            "other_income": other_income,
            "hra_exemption": hra_exemption,
            "chapter_via_manual": chapter_via_manual,
            "assessment_year": assessment_year,
            "warnings": [],
            "errors": [],
            "ocr_applied": False,
            "parsed_lines": 0,
        }

        for node in self.nodes:
            if node.name == "ocr_enhancer":
                (node.force) if hasattr(node, "force") else None
                if isinstance(node, OCREnhancer):
                    node.force = force_ocr or node.force

            try:
                ctx = node.process(ctx)
            except Exception as e:
                ctx.setdefault("errors", []).append(f"Node '{node.name}' failed: {e}")
                break

        elapsed = (time.perf_counter() - start) * 1000

        metadata = PipelineMetadata(
            processing_time_ms=round(elapsed, 2),
            ocr_applied=ctx.get("ocr_applied", False),
            parsed_lines=ctx.get("parsed_lines", 0),
            warnings=ctx.get("warnings", []),
        )

        return PipelineResult(
            form16=ctx.get("form16"),
            tax_comparison=ctx.get("tax_comparison"),
            summary_pdf=ctx.get("summary_pdf", b""),
            demo_xml=ctx.get("demo_xml", ""),
            metadata=metadata,
            errors=ctx.get("errors", []),
        )
