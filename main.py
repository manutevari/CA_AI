#!/usr/bin/env python3
"""ITR Filing Automator — pure Python CLI powered by the pipeline + pydantic models.

Parse a Form 16 PDF, compare old vs new regime (simplified FY 2024-25 / AY 2025-26),
write a summary PDF and a demo ITR-1-style XML.

Examples:
  python main.py path/to/Form16.pdf --out-dir ./out
  python main.py path/to/Form16.pdf --ocr --other-income 12000 --hra 80000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline import TaxPipeline


def main() -> int:
    p = argparse.ArgumentParser(
        description="Form 16 → tax comparison → PDF + demo XML (pipeline).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  python main.py path/to/Form16.pdf\n  python main.py Form16.pdf --out-dir ./out --json",
    )
    p.add_argument("form16_pdf", type=Path, nargs="?", default=None, help="Path to Form 16 PDF")
    p.add_argument("--out-dir", type=Path, default=Path("."), help="Output directory")
    p.add_argument("--ocr", action="store_true", help="Force OCR for scanned PDFs (needs Tesseract)")
    p.add_argument("--other-income", type=float, default=0.0, dest="other_income")
    p.add_argument("--hra", type=float, default=0.0, help="HRA exemption for old regime")
    p.add_argument(
        "--chapter-via", type=float, default=None, dest="chapter_via",
        help="Override Chapter VI-A total for old regime",
    )
    p.add_argument("--json", action="store_true", help="Print JSON summary to stdout")
    args = p.parse_args()

    pdf_path: Path | None = args.form16_pdf
    if pdf_path is None:
        p.print_help()
        print("\nMissing Form 16 path: pass your PDF as the first argument.", file=sys.stderr)
        return 2

    if not pdf_path.is_file():
        print(f"Error: file not found: {pdf_path}", file=sys.stderr)
        return 1

    data = pdf_path.read_bytes()

    pipeline = TaxPipeline()
    result = pipeline.run(
        data,
        other_income=args.other_income,
        hra_exemption=args.hra,
        chapter_via_manual=args.chapter_via,
        force_ocr=args.ocr,
    )

    if result.errors:
        for err in result.errors:
            print(f"Error: {err}", file=sys.stderr)
        return 1

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    pdf_out = out_dir / "itr_mvp_summary.pdf"
    xml_out = out_dir / "itr1_demo_prefill.xml"

    pdf_out.write_bytes(result.summary_pdf)
    xml_out.write_text(result.demo_xml, encoding="utf-8")

    print(f"Wrote {pdf_out.resolve()}")
    print(f"Wrote {xml_out.resolve()}")

    if result.tax_comparison:
        print(f"Suggested regime: {result.tax_comparison.recommended}")
        print(f"  New regime tax: ₹ {result.tax_comparison.new_regime.total_tax:,.2f}")
        print(f"  Old regime tax: ₹ {result.tax_comparison.old_regime.total_tax:,.2f}")

    for w in result.metadata.warnings:
        print(f"Warning: {w}", file=sys.stderr)

    if args.json:
        print(json.dumps(result.to_report(), indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
