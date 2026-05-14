"""Agentic filing-readiness assessment for the Streamlit demo."""

from __future__ import annotations

import re
from typing import Any

from agent_provider import choose_provider, provider_status, reason_with_best_model, tavily_search
from form16_parser import Form16Extract
from tax_engine import TaxResult

PAN_RE = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")
TDS_RECON_TOLERANCE = 100.0

PLAN = [
    {"id": "collect_evidence", "title": "Collect Form 16 and taxpayer inputs"},
    {"id": "extract_fields", "title": "Extract and normalize tax fields"},
    {"id": "reconcile_credits", "title": "Reconcile TDS with AIS / 26AS"},
    {"id": "validate_rules", "title": "Run deterministic Indian tax rules"},
    {"id": "choose_provider", "title": "Choose Tavily / LLM provider dynamically"},
    {"id": "score_confidence", "title": "Score filing confidence"},
    {"id": "human_review", "title": "Create CA review checkpoints"},
    {"id": "schema_gate", "title": "Block until official CBDT schema validation passes"},
]


def assess_filing_readiness(
    *,
    form16: Form16Extract,
    selected_regime: str,
    chosen_tax: TaxResult,
    other_income: float,
    hra_exemption: float,
    chapter_via: float,
    ais_tds: float | None = None,
    form26as_tds: float | None = None,
    official_schema_validation_passed: bool = False,
    portal_submission_authorized: bool = False,
    enable_live_search: bool = False,
    enable_llm_reasoning: bool = False,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    corrections: list[dict[str, Any]] = []
    pan = (form16.pan or "").strip().upper()

    if form16.pan and form16.pan != pan:
        corrections.append(
            {
                "field": "pan",
                "before": form16.pan,
                "after": pan,
                "reason": "Normalize PAN casing and whitespace.",
                "requires_review": False,
            }
        )
    if pan and not PAN_RE.match(pan):
        findings.append(_finding("PAN_FORMAT", "error", "PAN format is invalid.", "pan", review=True))
    if form16.gross_salary > 250_000 and form16.tds_deducted <= 0:
        findings.append(
            _finding(
                "MISSING_TDS",
                "warn",
                "Salary is material but extracted TDS is zero; verify Form 16 Part B and AIS/26AS.",
                "tds_deducted",
                review=True,
            )
        )
    if form16.tds_deducted > form16.gross_salary > 0:
        findings.append(
            _finding(
                "TDS_EXCEEDS_GROSS_SALARY",
                "error",
                "TDS exceeds gross salary; extracted values need human review.",
                "tds_deducted",
                review=True,
            )
        )
    if selected_regime == "new" and chapter_via > 0:
        findings.append(
            _finding(
                "NEW_REGIME_VIA_REVIEW",
                "warn",
                "Chapter VI-A deductions are present while the new regime is selected; verify final regime choice.",
                "chapter_via",
                review=True,
            )
        )
    if selected_regime == "new" and hra_exemption > 0:
        findings.append(
            _finding(
                "NEW_REGIME_HRA_REVIEW",
                "warn",
                "HRA exemption is present while the new regime is selected; verify final regime choice.",
                "hra_exemption",
                review=True,
            )
        )

    findings.extend(_reconcile_tds(form16.tds_deducted, ais_tds, form26as_tds))

    if not official_schema_validation_passed:
        findings.append(
            _finding(
                "CBDT_SCHEMA_VALIDATION_REQUIRED",
                "critical",
                "Official CBDT JSON/XML schema validation has not passed; demo XML must not be treated as a filed return.",
                "official_schema_validation_passed",
                review=True,
            )
        )
    if not portal_submission_authorized:
        findings.append(
            _finding(
                "PORTAL_AUTHORIZATION_REQUIRED",
                "warn",
                "Direct portal filing requires explicit taxpayer authorization and is not enabled in this demo.",
                "portal_submission_authorized",
                review=True,
            )
        )

    search_choice = choose_provider("official_search")
    reasoning_choice = choose_provider("tax_reasoning")
    live_search = None
    if enable_live_search and search_choice.name == "tavily":
        live_search = tavily_search("latest official ITR forms download utility AY 2026-27 site:incometax.gov.in")

    llm_review = None
    if enable_llm_reasoning and reasoning_choice.name not in {"deterministic_rules", "local_rules"}:
        llm_review = reason_with_best_model(
            "You are a cautious Indian ITR filing review assistant. Do not claim legal certainty. Return concise review notes only.",
            _review_prompt(form16, selected_regime, chosen_tax, findings),
        )

    confidence = _score_confidence(findings, corrections, ais_tds, form26as_tds, bool(llm_review and not llm_review.get("error")))
    status = "blocked" if any(f["severity"] == "critical" for f in findings) else "needs_review"
    if status != "blocked" and confidence >= 0.9 and not any(f["requires_review"] for f in findings):
        status = "ready_for_schema_export"

    return {
        "status": status,
        "confidence": confidence,
        "plan": _plan_with_status(findings, confidence, search_choice.name, reasoning_choice.name),
        "findings": findings,
        "corrections": corrections,
        "review_checkpoints": [f for f in findings if f.get("requires_review")],
        "next_actions": _next_actions(findings, confidence),
        "provider_status": provider_status(),
        "provider_choices": {
            "official_search": search_choice.__dict__,
            "tax_reasoning": reasoning_choice.__dict__,
        },
        "live_search": _safe_search_summary(live_search),
        "llm_review": _safe_llm_review(llm_review),
        "summary": {
            "selected_regime": selected_regime,
            "other_income": max(0.0, other_income),
            "chapter_via": max(0.0, chapter_via),
            "ais_tds": ais_tds,
            "form26as_tds": form26as_tds,
        },
    }


def _reconcile_tds(tds: float, ais_tds: float | None, form26as_tds: float | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if tds and ais_tds is None and form26as_tds is None:
        findings.append(
            _finding(
                "AIS_26AS_MISSING",
                "warn",
                "TDS is present but AIS/26AS values were not provided for reconciliation.",
                "ais_tds",
                review=True,
            )
        )
    for label, value in (("AIS", ais_tds), ("FORM26AS", form26as_tds)):
        if value is None or not tds:
            continue
        tolerance = max(TDS_RECON_TOLERANCE, tds * 0.01)
        if abs(value - tds) > tolerance:
            findings.append(
                _finding(
                    f"{label}_TDS_MISMATCH",
                    "error",
                    f"{label} TDS does not reconcile with Form 16 TDS within tolerance.",
                    f"{label.lower()}_tds",
                    review=True,
                )
            )
    return findings


def _score_confidence(
    findings: list[dict[str, Any]],
    corrections: list[dict[str, Any]],
    ais_tds: float | None,
    form26as_tds: float | None,
    llm_reviewed: bool,
) -> float:
    score = 0.86
    if ais_tds is not None or form26as_tds is not None:
        score += 0.06
    if llm_reviewed:
        score += 0.03
    if corrections:
        score -= min(0.08, len(corrections) * 0.03)
    penalties = {"critical": 0.24, "error": 0.14, "warn": 0.06, "info": 0.02}
    for finding in findings:
        score -= penalties.get(finding["severity"], 0.03)
    return round(max(0.0, min(1.0, score)), 3)


def _plan_with_status(
    findings: list[dict[str, Any]], confidence: float, search_provider: str, reasoning_provider: str
) -> list[dict[str, Any]]:
    blocked = any(f["severity"] == "critical" for f in findings)
    plan: list[dict[str, Any]] = []
    for step in PLAN:
        status = "completed"
        detail = None
        if step["id"] == "choose_provider":
            detail = f"search={search_provider}, reasoning={reasoning_provider}"
        if step["id"] in {"human_review", "schema_gate"} and (blocked or confidence < 0.9):
            status = "pending"
        row = {**step, "status": status}
        if detail:
            row["detail"] = detail
        plan.append(row)
    return plan


def _next_actions(findings: list[dict[str, Any]], confidence: float) -> list[str]:
    actions: list[str] = []
    codes = {f["code"] for f in findings}
    if "AIS_26AS_MISSING" in codes:
        actions.append("Upload or enter AIS/26AS TDS values before final review.")
    if "CBDT_SCHEMA_VALIDATION_REQUIRED" in codes:
        actions.append("Run official CBDT schema validation before filing.")
    if confidence < 0.9:
        actions.append("Route this filing to CA/human review.")
    if not actions:
        actions.append("Proceed to official schema generation gate.")
    return actions


def _review_prompt(form16: Form16Extract, selected_regime: str, chosen_tax: TaxResult, findings: list[dict[str, Any]]) -> str:
    return (
        f"PAN present: {bool(form16.pan)}\n"
        f"Gross salary: {form16.gross_salary}\n"
        f"TDS: {form16.tds_deducted}\n"
        f"Regime: {selected_regime}\n"
        f"Taxable income: {chosen_tax.taxable_income}\n"
        f"Total tax: {chosen_tax.total_tax}\n"
        f"Findings: {findings}\n"
        "Give short review notes and missing evidence only."
    )


def _safe_search_summary(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not result:
        return None
    return {
        "answer": result.get("answer"),
        "results": [
            {"title": item.get("title"), "url": item.get("url")}
            for item in result.get("results", [])[:5]
            if isinstance(item, dict)
        ],
    }


def _safe_llm_review(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not result:
        return None
    return {
        "provider": result.get("provider"),
        "model": result.get("model"),
        "content": result.get("content"),
        "error": result.get("error"),
    }


def _finding(code: str, severity: str, message: str, field: str, *, review: bool) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "field": field,
        "requires_review": review,
    }
