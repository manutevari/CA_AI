"""TaxPilot AI — Streamlit demo: Form 16 upload, extraction, dual-regime tax, PDF + demo XML.

Deploy on Streamlit Community Cloud: set Main file to `app.py`, use root `requirements.txt` + `packages.txt`.
"""

from __future__ import annotations

import streamlit as st

from agent_provider import provider_status
from agent_readiness import assess_filing_readiness
from form16_parser import Form16Extract, extract_text_from_pdf_bytes, ocr_pdf_page_images, parse_form16_text
from itr_xml import build_itr1_demo_xml
from official_itr_forms import (
    CURRENT_ONLINE_FORMS,
    EFILE_HOME_URL,
    EFILE_LOGIN_URL,
    LATEST_DOWNLOAD_UTILITIES,
    NOTIFIED_FORMS_URL,
    OFFICIAL_DOWNLOADS_URL,
    OFFICIAL_ONLINE_ITR_URL,
    recommend_itr_form,
)
from pdf_export import build_summary_pdf
from tax_engine import TaxInputs, compare_regimes

st.set_page_config(page_title="TaxPilot AI (Streamlit)", layout="wide")

st.title("TaxPilot AI — Streamlit filing lab")
st.caption(
    "Upload Form 16 (PDF), review extracted fields, compare tax regimes, export a summary PDF "
    "and a demo ITR-1-style XML. **Not legal or tax advice.** "
    "Full-stack product scaffold lives in `backend/` + `frontend/` (Docker)."
)

with st.expander("Official ITR forms, download utilities, and online filing", expanded=True):
    st.markdown(
        "Official filing must happen through the Income Tax Department portal or its official utilities. "
        "For FY 2025-26 income, select **AY 2026-27** on the portal. The portal currently exposes online "
        "filing help for AY 2026-27 and downloadable offline utilities on the official downloads page."
    )
    q1, q2, q3 = st.columns(3)
    with q1:
        form_total_income = st.number_input("Expected total income for form check (₹)", min_value=0.0, value=0.0, step=50000.0)
    with q2:
        form_has_business = st.checkbox("Business / profession income", value=False)
        form_presumptive = st.checkbox("Eligible presumptive income", value=False, disabled=not form_has_business)
    with q3:
        form_has_capital_gains = st.checkbox("Capital gains beyond ITR-1 scope", value=False)
    recommended_form = recommend_itr_form(
        has_business_income=form_has_business,
        presumptive_taxation=form_presumptive,
        has_capital_gains=form_has_capital_gains,
        total_income=form_total_income,
    )
    st.success(f"Suggested starting form: {recommended_form}. Confirm eligibility on the official portal before filing.")

    action_cols = st.columns(4)
    action_cols[0].link_button("Fill online", EFILE_LOGIN_URL, use_container_width=True)
    action_cols[1].link_button("ITR online help", OFFICIAL_ONLINE_ITR_URL, use_container_width=True)
    action_cols[2].link_button("Download utilities", OFFICIAL_DOWNLOADS_URL, use_container_width=True)
    action_cols[3].link_button("Notified form PDFs", NOTIFIED_FORMS_URL, use_container_width=True)

    st.write("**Forms for online filing**")
    for form in CURRENT_ONLINE_FORMS:
        with st.container(border=True):
            left, right = st.columns([3, 1])
            left.markdown(f"**{form.form} - {form.title}**")
            left.caption(form.applies_to)
            if form.notes:
                left.info(form.notes)
            if form.online_help_url:
                right.link_button("Open", form.online_help_url, use_container_width=True)

    st.write("**Latest official download utilities listed by portal**")
    for form in LATEST_DOWNLOAD_UTILITIES:
        with st.container(border=True):
            left, right = st.columns([3, 1])
            left.markdown(f"**{form.form} - {form.title}**")
            left.caption(form.applies_to)
            if form.latest_release:
                left.write(f"Latest release shown on portal: {form.latest_release}")
            if form.notes:
                left.caption(form.notes)
            if form.download_url:
                right.link_button("Download", form.download_url, use_container_width=True)
            if form.schema_url:
                right.link_button("Schema", form.schema_url, use_container_width=True)

    st.warning(
        "This app can help prepare and review data, but it does not replace official CBDT schema validation, "
        "portal submission, e-verification, or CA/tax professional review."
    )
    st.caption(f"Official e-filing forms landing page: {EFILE_HOME_URL}")

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

with st.expander("Dynamic agent provider routing", expanded=False):
    st.caption(
        "The agent reads keys from Streamlit secrets or environment variables and chooses the provider by task. "
        "Secret values are never displayed."
    )
    st.dataframe(provider_status(), use_container_width=True, hide_index=True)
    p1, p2 = st.columns(2)
    with p1:
        enable_live_search = st.checkbox("Use Tavily for live official-source search", value=False)
        ais_tds_raw = st.number_input("AIS TDS credit (optional)", min_value=0.0, value=0.0, step=500.0)
        form26as_tds_raw = st.number_input("Form 26AS TDS credit (optional)", min_value=0.0, value=0.0, step=500.0)
    with p2:
        enable_llm_reasoning = st.checkbox("Use best configured LLM for review notes", value=False)
        official_schema_validation_passed = st.checkbox("Official CBDT schema validation passed", value=False)
        portal_submission_authorized = st.checkbox("Taxpayer portal filing authorization recorded", value=False)
    st.code(
        "TAVILY_KEY or tavily_key\nHF_API_KEY\nDEEPSEEK_API_KEY\nGROQ_API_KEY\nMISTRAL_API_KEY",
        language="text",
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

    regime_pick = st.radio(
        "Regime for demo XML and agent review",
        options=["new", "old"],
        index=0 if rec == "new" else 1,
        horizontal=True,
    )
    chosen = new_r if regime_pick == "new" else old_r

    readiness = assess_filing_readiness(
        form16=merged,
        selected_regime=regime_pick,
        chosen_tax=chosen,
        other_income=other_income,
        hra_exemption=hra_exemption,
        chapter_via=merged.total_80c,
        ais_tds=ais_tds_raw if ais_tds_raw > 0 else None,
        form26as_tds=form26as_tds_raw if form26as_tds_raw > 0 else None,
        official_schema_validation_passed=official_schema_validation_passed,
        portal_submission_authorized=portal_submission_authorized,
        enable_live_search=enable_live_search,
        enable_llm_reasoning=enable_llm_reasoning,
    )

    st.subheader("Agentic filing readiness")
    a1, a2, a3 = st.columns(3)
    a1.metric("Readiness status", readiness["status"].replace("_", " ").title())
    a2.metric("Confidence", f"{readiness['confidence']:.0%}")
    a3.metric("Review checkpoints", len(readiness["review_checkpoints"]))
    st.progress(readiness["confidence"])

    tab_plan, tab_findings, tab_providers, tab_actions = st.tabs(["Plan", "Findings", "Providers", "Next actions"])
    with tab_plan:
        st.dataframe(readiness["plan"], use_container_width=True, hide_index=True)
    with tab_findings:
        if readiness["findings"]:
            st.dataframe(readiness["findings"], use_container_width=True, hide_index=True)
        else:
            st.success("No deterministic rule findings in this demo assessment.")
        if readiness["corrections"]:
            st.write("**Correction proposals**")
            st.json(readiness["corrections"])
    with tab_providers:
        st.write("**Chosen providers**")
        st.json(readiness["provider_choices"])
        if readiness["live_search"]:
            st.write("**Tavily official-source search**")
            st.json(readiness["live_search"])
        if readiness["llm_review"]:
            st.write("**LLM review notes**")
            st.json(readiness["llm_review"])
    with tab_actions:
        for action in readiness["next_actions"]:
            st.warning(action)

    pdf_bytes = build_summary_pdf(merged, new_r, old_r, recommended="new" if rec == "new" else "old")
    st.download_button(
        "Download summary PDF",
        data=pdf_bytes,
        file_name="itr_mvp_summary.pdf",
        mime="application/pdf",
    )

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
