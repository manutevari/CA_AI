"""TaxPilot AI — Streamlit demo: Form 16 upload, extraction, dual-regime tax, PDF + demo XML.

Deploy on Streamlit Community Cloud: set Main file to `app.py`, use root `requirements.txt` + `packages.txt`.
"""

from __future__ import annotations

import streamlit as st

from form16_parser import Form16Extract, extract_text_from_pdf_bytes, ocr_pdf_page_images, parse_form16_text
from itr_xml import build_itr1_demo_xml
from pdf_export import build_summary_pdf
from tax_engine import TaxInputs, compare_regimes

st.set_page_config(page_title="TaxPilot AI (Streamlit)", layout="wide")

st.title("TaxPilot AI — Streamlit filing lab")
st.caption(
    "Upload Form 16 (PDF), review extracted fields, compare tax regimes, export a summary PDF "
    "and a demo ITR-1-style XML. **Not legal or tax advice.** "
    "Full-stack product scaffold lives in `backend/` + `frontend/` (Docker)."
)

uploaded = st.file_uploader("Form 16 (PDF)", type=["pdf"])
force_ocr = st.checkbox(
    "Force OCR (scanned PDFs — requires [Tesseract](https://github.com/tesseract-ocr/tesseract) installed)",
    value=False,
)

col_a, col_b = st.columns(2)
with col_a:
    other_income = st.number_input("Other income (₹)", min_value=0.0, value=0.0, step=1000.0)
    hra_exemption = st.number_input("HRA exemption — old regime (₹)", min_value=0.0, value=0.0, step=5000.0)
with col_b:
    chapter_via_manual = st.number_input(
        "Chapter VI-A total (80C+80D+…) — old regime (₹)",
        min_value=0.0,
        value=0.0,
        step=5000.0,
        help="If Form 16 parsing misses deductions, enter manually.",
    )

if uploaded is not None:
    data = uploaded.getvalue()

    text, file_hash = extract_text_from_pdf_bytes(data)
    if force_ocr or len(text.strip()) < 50:
        try:
            ocr_text = ocr_pdf_page_images(data)
            if len(ocr_text.strip()) > len(text.strip()):
                text = ocr_text
        except Exception as exc:  # noqa: BLE001
            st.warning(f"OCR unavailable or failed: {exc}. Using PDF text layer only.")

    extracted = parse_form16_text(text, file_hash)

    st.subheader("Parsed Form 16 (editable)")
    c1, c2, c3 = st.columns(3)
    pan = c1.text_input("PAN", value=extracted.pan or "")
    emp_name = c2.text_input("Employee name", value=extracted.employee_name or "")
    er_name = c3.text_input("Employer name", value=extracted.employer_name or "")
    g1, g2, g3 = st.columns(3)
    gross = g1.number_input(
        "Gross salary (₹)", min_value=0.0, value=float(extracted.gross_salary or 0), step=5000.0
    )
    tds = g2.number_input(
        "TDS deducted (₹)", min_value=0.0, value=float(extracted.tds_deducted or 0), step=500.0
    )
    c80 = g3.number_input(
        "80C / VI-A used in old regime (₹)",
        min_value=0.0,
        value=float(max(extracted.total_80c, chapter_via_manual)),
        step=5000.0,
    )

    for w in extracted.parse_warnings:
        st.warning(w)

    merged = Form16Extract(
        pan=pan or None,
        employee_name=emp_name or None,
        employer_name=er_name or None,
        gross_salary=gross,
        tds_deducted=tds,
        total_80c=min(c80, 200_000),
        raw_text_sample=extracted.raw_text_sample,
        parse_warnings=extracted.parse_warnings,
        sha256=extracted.sha256,
    )

    inputs = TaxInputs(
        gross_salary=merged.gross_salary,
        standard_deduction=0.0,
        chapter_via=merged.total_80c,
        hra_exemption=hra_exemption,
        other_income=other_income,
    )
    new_r, old_r = compare_regimes(inputs, merged.tds_deducted)
    rec = "new" if new_r.total_tax <= old_r.total_tax else "old"

    st.subheader("Regime comparison (simplified FY 2024-25 / AY 2025-26)")
    m1, m2, m3 = st.columns(3)
    m1.metric("New regime tax (incl. cess)", f"₹ {new_r.total_tax:,.0f}")
    m2.metric("Old regime tax (incl. cess)", f"₹ {old_r.total_tax:,.0f}")
    m3.metric("Suggested regime", "New" if rec == "new" else "Old")

    d1, d2 = st.columns(2)
    with d1:
        st.write("**New regime**")
        st.json(
            {
                "taxable_income": new_r.taxable_income,
                "rebate_87A": new_r.rebate_87a,
                "total_tax": new_r.total_tax,
                "refund_or_payable": new_r.refund_or_payable,
            }
        )
    with d2:
        st.write("**Old regime**")
        st.json(
            {
                "taxable_income": old_r.taxable_income,
                "rebate_87A": old_r.rebate_87a,
                "total_tax": old_r.total_tax,
                "refund_or_payable": old_r.refund_or_payable,
            }
        )

    pdf_bytes = build_summary_pdf(merged, new_r, old_r, recommended="new" if rec == "new" else "old")
    st.download_button(
        "Download summary PDF",
        data=pdf_bytes,
        file_name="itr_mvp_summary.pdf",
        mime="application/pdf",
    )

    regime_pick = st.radio(
        "Regime for demo XML", options=["new", "old"], index=0 if rec == "new" else 1, horizontal=True
    )
    chosen = new_r if regime_pick == "new" else old_r
    xml_text = build_itr1_demo_xml(merged, chosen)
    st.download_button(
        "Download demo ITR-1-style XML",
        data=xml_text.encode("utf-8"),
        file_name="itr1_demo_prefill.xml",
        mime="application/xml",
    )

    with st.expander("Raw extracted text (first 3000 chars)"):
        st.code(text[:3000])

else:
    st.info("Upload a Form 16 PDF to begin.")

st.divider()
st.markdown(
    "**Deploy:** This app is built for [Streamlit Community Cloud](https://share.streamlit.io) "
    "(Main file `app.py`, root `requirements.txt`, `packages.txt` for Tesseract). "
    "**Full API:** run `docker compose up` or `uvicorn api:app` from repo root for the legacy `api.py` demo."
)
