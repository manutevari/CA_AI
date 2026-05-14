"""Simplified Indian income tax computation with numpy-accelerated slabs.

Not legal advice. Slabs default to FY 2024-25 (AY 2025-26) approximations.
"""

from __future__ import annotations

import numpy as np

from models import Regime, RegimeComparison, TaxInputs, TaxResult


def _cess(amount: float) -> float:
    return round(float(amount) * 0.04, 2)


def _slab_tax_old(taxable: float) -> float:
    """Old regime slabs via numpy vectorized computation."""
    if taxable <= 0:
        return 0.0
    limits = np.array([250_000, 250_000, 500_000], dtype=np.float64)
    rates = np.array([0.0, 0.05, 0.20], dtype=np.float64)
    r = float(taxable)
    tax = 0.0
    for limit, rate in zip(limits, rates):
        chunk = min(r, float(limit))
        tax += chunk * float(rate)
        r -= chunk
        if r <= 0:
            return round(tax, 2)
    tax += r * 0.30
    return round(tax, 2)


def _slab_tax_new(taxable: float) -> float:
    """New regime slabs via numpy — FY 2024-25 progressive rates."""
    if taxable <= 0:
        return 0.0
    limits = np.array([300_000, 400_000, 300_000, 200_000, 300_000], dtype=np.float64)
    rates = np.array([0.0, 0.05, 0.10, 0.15, 0.20], dtype=np.float64)
    r = float(taxable)
    tax = 0.0
    for limit, rate in zip(limits, rates):
        chunk = min(r, float(limit))
        tax += chunk * float(rate)
        r -= chunk
        if r <= 0:
            return round(tax, 2)
    tax += r * 0.30
    return round(tax, 2)


def _rebate_87a_old(income_after_deductions: float, tax_before: float) -> float:
    return min(tax_before, 12_500) if income_after_deductions <= 500_000 else 0.0


def _rebate_87a_new(total_income: float, tax_before: float) -> float:
    return min(tax_before, 25_000) if total_income <= 700_000 else 0.0


def compute_tax(inputs: TaxInputs, regime: Regime, tds_paid: float) -> TaxResult:
    gross_total = max(0.0, inputs.gross_salary + inputs.other_income)

    if regime == "new":
        std = max(inputs.standard_deduction, 75_000)
        taxable = max(0.0, round(gross_total - std, 2))
        tax_before = _slab_tax_new(taxable)
        rebate = _rebate_87a_new(taxable, tax_before)
    else:
        std = max(inputs.standard_deduction, 50_000)
        deductions = min(inputs.chapter_via, 150_000)
        taxable = max(0.0, round(gross_total - std - deductions - inputs.hra_exemption, 2))
        tax_before = _slab_tax_old(taxable)
        rebate = _rebate_87a_old(taxable, tax_before)

    tax_after = max(0.0, round(tax_before - rebate, 2))
    cess = _cess(tax_after)
    total_tax = round(tax_after + cess, 2)

    return TaxResult(
        regime=regime,
        gross_total=round(gross_total, 2),
        taxable_income=taxable,
        tax_before_cess=tax_before,
        rebate_87a=rebate,
        tax_after_rebate=tax_after,
        cess=cess,
        total_tax=total_tax,
        tds_credit=round(tds_paid, 2),
        refund_or_payable=round(tds_paid - total_tax, 2),
    )


def compare_regimes(inputs: TaxInputs, tds_paid: float) -> RegimeComparison:
    new_r = compute_tax(inputs, "new", tds_paid)
    old_r = compute_tax(inputs, "old", tds_paid)
    recommended: Regime = "new" if new_r.total_tax <= old_r.total_tax else "old"
    return RegimeComparison(new_regime=new_r, old_regime=old_r, recommended=recommended)
