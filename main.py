#!/usr/bin/env python3
"""ITR Filing Automator — pure Python CLI (no Streamlit).

Parse a Form 16 PDF, compare old vs new regime (simplified FY 2024-25 / AY 2025-26),
write a summary PDF and a demo ITR-1-style XML.

Example:
  python main.py path/to/Form16.pdf --out-dir ./out
  python main.py path/to/Form16.pdf --ocr --other-income 12000 --hra 80000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from form16_parser import Form16Extract, extract_text_from_pdf_bytes, ocr_pdf_page_images, parse_form16_text
from itr_xml import build_itr1_demo_xml
from pdf_export import build_summary_pdf
from tax_engine import TaxInputs, compare_regimes


def _read_pdf(path: Path) -> bytes:
    return path.read_bytes()


def _extract_text(data: bytes, use_ocr: bool) -> tuple[str, str]:
    text, file_hash = extract_text_from_pdf_bytes(data)
    if use_ocr or len(text.strip()) < 50:
        try:
            ocr_text = ocr_pdf_page_images(data)
            if len(ocr_text.strip()) > len(text.strip()):
                text = ocr_text
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: OCR failed ({exc}); using PDF text layer.", file=sys.stderr)
    return text, file_hash


def main() -> int:
    p = argparse.ArgumentParser(
        description="Form 16 → tax comparison → PDF + demo XML (MVP).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  python main.py C:\\\\Users\\\\You\\\\Downloads\\\\Form16.pdf\n  python main.py .\\\\Form16.pdf --out-dir .\\\\out --json",
    )
    p.add_argument(
        "form16_pdf",
        type=Path,
        nargs="?",
        default=None,
        help="Path to Form 16 PDF (required unless you only pass -h)",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("."),
        help="Directory for itr_mvp_summary.pdf and itr1_demo_prefill.xml",
    )
    p.add_argument("--ocr", action="store_true", help="Prefer OCR for scanned PDFs (needs Tesseract)")
    p.add_argument("--other-income", type=float, default=0.0, dest="other_income")
    p.add_argument("--hra", type=float, default=0.0, help="HRA exemption for old regime")
    p.add_argument(
        "--chapter-via",
        type=float,
        default=None,
        dest="chapter_via",
        help="Override Chapter VI-A total for old regime (80C+80D+…)",
    )
    p.add_argument("--json", action="store_true", help="Print JSON summary to stdout")
    args = p.parse_args()

    pdf_path: Path | None = args.form16_pdf
    if pdf_path is None:
        p.print_help()
        print(
            "\nMissing Form 16 path: pass your PDF as the first argument, e.g.\n"
            "  python main.py C:\\Users\\You\\Desktop\\Form16.pdf\n"
            "For the web UI instead, run: streamlit run app.py",
            file=sys.stderr,
        )
        return 2

    if not pdf_path.is_file():
        print(f"Error: file not found: {pdf_path}", file=sys.stderr)
        return 1

    data = _read_pdf(pdf_path)
    text, file_hash = _extract_text(data, args.ocr)
    parsed = parse_form16_text(text, file_hash)

    chapter_via = float(args.chapter_via) if args.chapter_via is not None else parsed.total_80c
    merged = Form16Extract(
        pan=parsed.pan,
        employee_name=parsed.employee_name,
        employer_name=parsed.employer_name,
        gross_salary=parsed.gross_salary,
        tds_deducted=parsed.tds_deducted,
        total_80c=min(chapter_via, 200_000),
        raw_text_sample=parsed.raw_text_sample,
        parse_warnings=parsed.parse_warnings,
        sha256=parsed.sha256,
    )

    inputs = TaxInputs(
        gross_salary=merged.gross_salary,
        standard_deduction=0.0,
        chapter_via=merged.total_80c,
        hra_exemption=max(0.0, args.hra),
        other_income=max(0.0, args.other_income),
    )
    new_r, old_r = compare_regimes(inputs, merged.tds_deducted)
    rec = "new" if new_r.total_tax <= old_r.total_tax else "old"
    chosen = new_r if rec == "new" else old_r

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_out = out_dir / "itr_mvp_summary.pdf"
    xml_out = out_dir / "itr1_demo_prefill.xml"

    pdf_out.write_bytes(build_summary_pdf(merged, new_r, old_r, recommended=rec))
    xml_out.write_text(build_itr1_demo_xml(merged, chosen), encoding="utf-8")

    print(f"Wrote {pdf_out.resolve()}")
    print(f"Wrote {xml_out.resolve()}")
    print(f"Suggested regime: {rec} (lower of two simplified computations)")
    if merged.parse_warnings:
        for w in merged.parse_warnings:
            print(f"Warning: {w}", file=sys.stderr)

    if args.json:
        payload = {
            "parsed": merged.to_dict(),
            "new_regime": {
                "taxable_income": new_r.taxable_income,
                "total_tax": new_r.total_tax,
                "refund_or_payable": new_r.refund_or_payable,
            },
            "old_regime": {
                "taxable_income": old_r.taxable_income,
                "total_tax": old_r.total_tax,
                "refund_or_payable": old_r.refund_or_payable,
            },
            "recommended": rec,
        }
        print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
