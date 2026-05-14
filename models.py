"""Pydantic models for the TaxPilot AI pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal

import numpy as np
from pydantic import BaseModel, Field, field_validator


Regime = Literal["new", "old"]


class Form16Extract(BaseModel):
    pan: str | None = None
    employer_name: str | None = None
    employee_name: str | None = None
    gross_salary: Annotated[float, Field(ge=0)] = 0.0
    tds_deducted: Annotated[float, Field(ge=0)] = 0.0
    total_80c: Annotated[float, Field(ge=0, le=200_000)] = 0.0
    raw_text_sample: str = ""
    parse_warnings: list[str] = Field(default_factory=list)
    sha256: str = ""

    @field_validator("pan")
    @classmethod
    def validate_pan(cls, v: str | None) -> str | None:
        if v and not (len(v) == 10 and v[:5].isalpha() and v[5:9].isdigit() and v[9].isalpha()):
            raise ValueError(f"Invalid PAN format: {v}")
        return v.upper() if v else v


class TaxInputs(BaseModel):
    gross_salary: Annotated[float, Field(ge=0)] = 0.0
    standard_deduction: Annotated[float, Field(ge=0)] = 0.0
    chapter_via: Annotated[float, Field(ge=0)] = 0.0
    hra_exemption: Annotated[float, Field(ge=0)] = 0.0
    other_income: Annotated[float, Field(ge=0)] = 0.0

    @property
    def gross_total(self) -> float:
        return self.gross_salary + self.other_income


class TaxResult(BaseModel):
    regime: Regime
    gross_total: Annotated[float, Field(ge=0)] = 0.0
    taxable_income: Annotated[float, Field(ge=0)] = 0.0
    tax_before_cess: Annotated[float, Field(ge=0)] = 0.0
    rebate_87a: Annotated[float, Field(ge=0)] = 0.0
    tax_after_rebate: Annotated[float, Field(ge=0)] = 0.0
    cess: Annotated[float, Field(ge=0)] = 0.0
    total_tax: Annotated[float, Field(ge=0)] = 0.0
    tds_credit: Annotated[float, Field(ge=0)] = 0.0
    refund_or_payable: float = 0.0


class RegimeComparison(BaseModel):
    new_regime: TaxResult
    old_regime: TaxResult
    recommended: Regime


class PipelineMetadata(BaseModel):
    processing_time_ms: float = 0.0
    ocr_applied: bool = False
    parsed_lines: int = 0
    warnings: list[str] = Field(default_factory=list)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )


class PipelineResult(BaseModel):
    form16: Form16Extract | None = None
    tax_comparison: RegimeComparison | None = None
    summary_pdf: bytes = b""
    demo_xml: str = ""
    metadata: PipelineMetadata = Field(default_factory=PipelineMetadata)
    errors: list[str] = Field(default_factory=list)

    def to_report(self) -> dict[str, Any]:
        return {
            "pan": self.form16.pan if self.form16 else None,
            "employee": self.form16.employee_name if self.form16 else None,
            "recommended_regime": self.tax_comparison.recommended if self.tax_comparison else None,
            "new_regime_tax": round(self.tax_comparison.new_regime.total_tax, 2) if self.tax_comparison else None,
            "old_regime_tax": round(self.tax_comparison.old_regime.total_tax, 2) if self.tax_comparison else None,
            "warnings": self.metadata.warnings,
            "errors": self.errors,
            "timestamp": self.metadata.timestamp,
        }
