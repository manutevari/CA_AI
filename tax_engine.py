"""Simplified Indian income tax computation for demo / MVP purposes only.

Not legal advice. Slabs default to FY 2024-25 (AY 2025-26) new vs old regime
approximations for salaried individuals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Regime = Literal["new", "old"]


def _cess(amount: float) -> float:
    return round(amount * 0.04, 2)


def _slab_tax_old(taxable: float) -> float:
    """Old regime slabs (individual < 60) — simplified."""
    if taxable <= 0:
        return 0.0
    tax = 0.0
    remaining = taxable
    # 0 - 2.5L @ 0
    slab1 = min(remaining, 250_000)
    remaining -= slab1
    if remaining <= 0:
        return round(tax, 2)
    # 2.5 - 5L @ 5%
    slab2 = min(remaining, 250_000)
    tax += slab2 * 0.05
    remaining -= slab2
    if remaining <= 0:
        return round(tax, 2)
    # 5 - 10L @ 20%
    slab3 = min(remaining, 500_000)
    tax += slab3 * 0.20
    remaining -= slab3
    if remaining <= 0:
        return round(tax, 2)
    # >10L @ 30%
    tax += remaining * 0.30
    return round(tax, 2)


def _slab_tax_new(taxable: float) -> float:
    """New regime slabs FY 2024-25 (AY 2025-26) — progressive, simplified."""
    if taxable <= 0:
        return 0.0
    tax = 0.0
    r = taxable
    # 0–3L nil, 3–7L 5%, 7–10L 10%, 10–12L 15%, 12–15L 20%, >15L 30%
    brackets = [
        (300_000, 0.0),
        (400_000, 0.05),
        (300_000, 0.10),
        (200_000, 0.15),
        (300_000, 0.20),
    ]
    for width, rate in brackets:
        chunk = min(r, width)
        tax += chunk * rate
        r -= chunk
        if r <= 0:
            return round(tax, 2)
    tax += r * 0.30
    return round(tax, 2)


def _rebate_87a_old(income_after_deductions: float, tax_before_rebate: float) -> float:
    """Simplified 87A for old regime (resident): income <= 5L, rebate up to 12500."""
    if income_after_deductions <= 500_000:
        return min(tax_before_rebate, 12_500)
    return 0.0


def _rebate_87a_new(total_income: float, tax_before_rebate: float) -> float:
    """New regime FY 24-25: income <= 7L, rebate up to 25000."""
    if total_income <= 700_000:
        return min(tax_before_rebate, 25_000)
    return 0.0


@dataclass
class TaxInputs:
    gross_salary: float
    standard_deduction: float
    chapter_via: float  # 80C, 80D, etc. lump sum for MVP
    hra_exemption: float
    other_income: float


@dataclass
class TaxResult:
    regime: Regime
    gross_total: float
    taxable_income: float
    tax_before_cess: float
    rebate_87a: float
    tax_after_rebate: float
    cess: float
    total_tax: float
    tds_credit: float
    refund_or_payable: float


def compute_tax(
    inputs: TaxInputs,
    regime: Regime,
    tds_paid: float,
) -> TaxResult:
    gross_total = max(0.0, inputs.gross_salary + inputs.other_income)

    if regime == "new":
        std = max(inputs.standard_deduction, 75_000)  # salaried default FY 24-25
        taxable = gross_total - std
        taxable = max(0.0, round(taxable, 2))
        tax_before = _slab_tax_new(taxable)
        rebate = _rebate_87a_new(taxable, tax_before)
        tax_after_rebate = max(0.0, round(tax_before - rebate, 2))
    else:
        std = max(inputs.standard_deduction, 50_000)
        deductions = min(inputs.chapter_via, 150_000)  # cap 80C-heavy MVP guard
        taxable = gross_total - std - deductions - inputs.hra_exemption
        taxable = max(0.0, round(taxable, 2))
        tax_before = _slab_tax_old(taxable)
        rebate = _rebate_87a_old(taxable, tax_before)
        tax_after_rebate = max(0.0, round(tax_before - rebate, 2))

    cess = _cess(tax_after_rebate)
    total_tax = round(tax_after_rebate + cess, 2)
    refund_or_payable = round(tds_paid - total_tax, 2)

    return TaxResult(
        regime=regime,
        gross_total=round(gross_total, 2),
        taxable_income=taxable,
        tax_before_cess=tax_before,
        rebate_87a=rebate,
        tax_after_rebate=tax_after_rebate,
        cess=cess,
        total_tax=total_tax,
        tds_credit=round(tds_paid, 2),
        refund_or_payable=refund_or_payable,
    )


def compare_regimes(inputs: TaxInputs, tds_paid: float) -> tuple[TaxResult, TaxResult]:
    new_r = compute_tax(inputs, "new", tds_paid)
    old_r = compute_tax(inputs, "old", tds_paid)
    return new_r, old_r
