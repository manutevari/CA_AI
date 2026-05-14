"""TaxPilot AI — Streamlit demo: pipeline-powered Form 16 upload, extraction, comparison, export."""

from __future__ import annotations

import streamlit as st

from pipeline import TaxPipeline

st.set_page_config(page_title="TaxPilot AI (Streamlit)", layout="wide")

st.title("TaxPilot AI — Streamlit filing lab")
st.caption(
    "Upload Form 16 (PDF), review extracted fields, compare tax regimes, export a summary PDF "
    "and a demo ITR-1-style XML. **Not legal or tax advice.**"
)

with st.expander("Status · compliance · preview", expanded=True):
    st.markdown("""
**This build is a technical preview / scaffold, not a certified product.**

| Check | Status |
|-------|--------|
| Enterprise compliance (SOC2, ISO27001, org policies) | Not met — design & controls TBD |
| Production hardening (SLOs, DR, secrets, pen-test) | Not met — demo-grade defaults |
| Legally complete e-filing (CBDT schema, e-verify, notices) | Not met — do not file real returns here |

**Local preview:**
- **Streamlit:** `streamlit run app.py` → [http://localhost:8501](http://localhost:8501)
- **Hosted:** deploy on [Streamlit Community Cloud](https://share.streamlit.io) (main file `app.py`)
    """)

uploaded = st.file_uploader("Form 16 (PDF)", type=["pdf"])
force_ocr = st.checkbox(
    "Force OCR (scanned PDFs — requires Tesseract installed)", value=False,
)

col_a, col_b = st.columns(2)
with col_a:
    other_income = st.number_input("Other income (₹)", min_value=0.0, value=0.0, step=1000.0)
    hra_exemption = st.number_input("HRA exemption — old regime (₹)", min_value=0.0, value=0.0, step=5000.0)
with col_b:
    chapter_via_manual = st.number_input(
        "Chapter VI-A total (80C+80D+…) — old regime (₹)",
        min_value=0.0, value=0.0, step=5000.0,
        help="If Form 16 parsing misses deductions, enter manually.",
    )

if uploaded is not None:
    data = uploaded.getvalue()
    pipeline = TaxPipeline()
    result = pipeline.run(
        data,
        other_income=other_income,
        hra_exemption=hra_exemption,
        chapter_via_manual=chapter_via_manual if chapter_via_manual > 0 else None,
        force_ocr=force_ocr,
    )

    if result.errors:
        for err in result.errors:
            st.error(err)
        st.stop()

    form16 = result.form16
    comparison = result.tax_comparison

    st.subheader("Parsed Form 16 (editable)")
    c1, c2, c3 = st.columns(3)
    pan = c1.text_input("PAN", value=form16.pan or "")
    emp_name = c2.text_input("Employee name", value=form16.employee_name or "")
    er_name = c3.text_input("Employer name", value=form16.employer_name or "")
    g1, g2, g3 = st.columns(3)
    gross = g1.number_input("Gross salary (₹)", min_value=0.0, value=float(form16.gross_salary or 0), step=5000.0)
    tds = g2.number_input("TDS deducted (₹)", min_value=0.0, value=float(form16.tds_deducted or 0), step=500.0)
    c80 = g3.number_input(
        "80C / VI-A used in old regime (₹)",
        min_value=0.0,
        value=float(max(form16.total_80c, chapter_via_manual)),
        step=5000.0,
    )

    for w in form16.parse_warnings:
        st.warning(w)

    st.subheader("Regime comparison (simplified FY 2024-25 / AY 2025-26)")
    m1, m2, m3 = st.columns(3)
    m1.metric("New regime tax (incl. cess)", f"₹ {comparison.new_regime.total_tax:,.0f}")
    m2.metric("Old regime tax (incl. cess)", f"₹ {comparison.old_regime.total_tax:,.0f}")
    m3.metric("Suggested regime", "New" if comparison.recommended == "new" else "Old")

    d1, d2 = st.columns(2)
    with d1:
        st.write("**New regime**")
        st.json({
            "taxable_income": comparison.new_regime.taxable_income,
            "rebate_87A": comparison.new_regime.rebate_87a,
            "total_tax": comparison.new_regime.total_tax,
            "refund_or_payable": comparison.new_regime.refund_or_payable,
        })
    with d2:
        st.write("**Old regime**")
        st.json({
            "taxable_income": comparison.old_regime.taxable_income,
            "rebate_87A": comparison.old_regime.rebate_87a,
            "total_tax": comparison.old_regime.total_tax,
            "refund_or_payable": comparison.old_regime.refund_or_payable,
        })

    st.download_button(
        "Download summary PDF",
        data=result.summary_pdf,
        file_name="itr_mvp_summary.pdf",
        mime="application/pdf",
    )

    regime_pick = st.radio(
        "Regime for demo XML", options=["new", "old"],
        index=0 if comparison.recommended == "new" else 1, horizontal=True,
    )
    st.download_button(
        "Download demo ITR-1-style XML",
        data=result.demo_xml.encode("utf-8"),
        file_name="itr1_demo_prefill.xml",
        mime="application/xml",
    )

    with st.expander(f"Pipeline metadata ({result.metadata.processing_time_ms} ms)"):
        st.json(result.metadata.model_dump())
else:
    st.info("Upload a Form 16 PDF to begin.")

st.divider()
st.markdown(
    "**Deploy:** This app is built for [Streamlit Community Cloud](https://share.streamlit.io) "
    "(Main file `app.py`, root `requirements.txt`, `packages.txt` for Tesseract)."
)
