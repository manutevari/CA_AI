#!/usr/bin/env python3
"""Cross-check repo readiness for Streamlit Community Cloud deployment.

Run from repository root:
  python verify_streamlit_deploy.py

Exits 0 if checks pass, 1 otherwise. Does not upload to Cloud — validates local prerequisites.
"""

from __future__ import annotations

import ast
import importlib
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent

REQUIRED_FILES = [
    "app.py",
    "requirements.txt",
    "packages.txt",
    ".streamlit/config.toml",
    "form16_parser.py",
    "tax_engine.py",
    "itr_xml.py",
    "pdf_export.py",
]

OPTIONAL_FILES = ["runtime.txt", "DEPLOY.txt"]


def check_python_version() -> list[str]:
    """Streamlit Cloud uses supported CPython; very new versions may lack wheels."""
    warnings: list[str] = []
    v = sys.version_info
    if v < (3, 10):
        warnings.append(f"Python {v.major}.{v.minor} is below 3.10 — Streamlit may not support it.")
    if v >= (3, 14):
        warnings.append(
            f"Python {v.major}.{v.minor} is very new — some wheels (streamlit/pymupdf) may be missing; "
            "prefer 3.11–3.12 for local dev to match Cloud."
        )
    return warnings


def check_files() -> list[str]:
    errors: list[str] = []
    for name in REQUIRED_FILES:
        path = ROOT / name
        if not path.is_file():
            errors.append(f"Missing required file: {path.relative_to(ROOT)}")
    return errors


def check_requirements_has_streamlit() -> list[str]:
    req = ROOT / "requirements.txt"
    if not req.is_file():
        return ["requirements.txt missing"]
    text = req.read_text(encoding="utf-8").lower()
    if "streamlit" not in text:
        return ["requirements.txt must list streamlit for Cloud"]
    return []


def check_app_syntax() -> list[str]:
    path = ROOT / "app.py"
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [f"app.py syntax error: {exc}"]
    return []


def check_imports() -> list[str]:
    """Import the same stack Cloud will pip-install (must be installed in current env)."""
    errors: list[str] = []
    modules = [
        "streamlit",
        "pdfplumber",
        "PIL",
        "reportlab",
        "fitz",  # pymupdf
        "pytesseract",
    ]
    for mod in modules:
        try:
            __import__(mod)
        except ImportError as exc:
            errors.append(f"Import failed ({mod}): {exc} — run: pip install -r requirements.txt")
    return errors


def check_project_modules() -> list[str]:
    """Import repo-root modules after deps (avoids exec_module edge cases on some Python builds)."""
    errors: list[str] = []
    root_str = str(ROOT)
    inserted = False
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
        inserted = True
    try:
        for name in ("form16_parser", "tax_engine", "itr_xml", "pdf_export"):
            try:
                importlib.import_module(name)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"import {name}: {exc}")
    finally:
        if inserted and sys.path and sys.path[0] == root_str:
            sys.path.pop(0)
    return errors


def check_tesseract_cli() -> list[str]:
    """packages.txt installs tesseract on Cloud; locally warn if binary missing."""
    if shutil.which("tesseract") is None:
        return [
            "Optional: `tesseract` CLI not on PATH — OCR checkbox may fail locally; "
            "Streamlit Cloud installs it via packages.txt."
        ]
    return []


def main() -> int:
    print(f"Streamlit deploy cross-check (root: {ROOT})")
    print(f"Python: {sys.version.split()[0]}\n")
    all_errors: list[str] = []
    warnings: list[str] = []

    warnings.extend(check_python_version())
    all_errors.extend(check_files())
    all_errors.extend(check_requirements_has_streamlit())
    all_errors.extend(check_app_syntax())

    missing_optional = [p for p in OPTIONAL_FILES if not (ROOT / p).is_file()]
    if missing_optional:
        warnings.append("Optional files not present: " + ", ".join(missing_optional))

    all_errors.extend(check_imports())
    all_errors.extend(check_project_modules())
    warnings.extend(check_tesseract_cli())

    for w in warnings:
        print(f"WARN  {w}")
    if warnings:
        print()

    if all_errors:
        print("FAIL  Issues:\n")
        for e in all_errors:
            print(f"  - {e}")
        print("\nFix errors, then redeploy on https://share.streamlit.io (Main file: app.py).")
        return 1

    print("PASS  Files, app.py syntax, requirements.txt, and imports look OK for Streamlit Cloud.")
    print("      Cloud still needs: GitHub repo, New app, main file app.py, branch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
