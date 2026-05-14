"""Export a human-readable filing summary PDF (not an official ITR PDF)."""

from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from models import Form16Extract, TaxResult


def build_summary_pdf(
    form16: Form16Extract,
    new_r: TaxResult,
    old_r: TaxResult,
    recommended: str,
) -> bytes:
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

    block("New regime (simplified FY 2024-25)", new_r)
    block("Old regime (simplified FY 2024-25)", old_r)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(2 * cm, y, f"Suggested regime (lower liability): {recommended}")
    y -= 0.8 * cm
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(
        2 * cm, y,
        "Disclaimer: Demo tool only. Verify with a qualified tax professional before filing.",
    )
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
