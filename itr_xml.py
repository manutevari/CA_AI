"""Simplified ITR-1-style XML prefill for demo — not CBDT schema certified."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.dom import minidom

from models import Form16Extract, TaxResult


def build_itr1_demo_xml(
    form16: Form16Extract,
    chosen: TaxResult,
    assessment_year: str = "2025-26",
) -> str:
    root = ET.Element(
        "ITRReturn",
        {
            "xmlns": "https://incometaxindia.gov.in/demo/mvp",
            "Form": "ITR-1",
            "AssessmentYear": assessment_year,
        },
    )
    ET.SubElement(root, "PAN").text = form16.pan or ""
    ET.SubElement(root, "EmployeeName").text = form16.employee_name or ""
    ET.SubElement(root, "EmployerName").text = form16.employer_name or ""
    inc = ET.SubElement(root, "Income")
    ET.SubElement(inc, "Salary").text = f"{form16.gross_salary:.2f}"
    ET.SubElement(inc, "OtherIncome").text = "0.00"
    ded = ET.SubElement(root, "DeductionsChapterVIA")
    ET.SubElement(ded, "Total80C").text = f"{form16.total_80c:.2f}"
    tax = ET.SubElement(root, "TaxComputation", {"Regime": chosen.regime})
    ET.SubElement(tax, "TaxableIncome").text = f"{chosen.taxable_income:.2f}"
    ET.SubElement(tax, "TotalTax").text = f"{chosen.total_tax:.2f}"
    ET.SubElement(tax, "TDSCredit").text = f"{chosen.tds_credit:.2f}"
    ET.SubElement(tax, "RefundOrPayable").text = f"{chosen.refund_or_payable:.2f}"

    rough = ET.tostring(root, encoding="unicode")
    parsed = minidom.parseString(rough)
    return parsed.toprettyxml(indent="  ")
