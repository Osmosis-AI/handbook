#!/bin/bash
set -euo pipefail
set -euo pipefail

python -c 'import openpyxl, pdfplumber, pypdf, reportlab, docx'
python /tests/sop_verifier.py
python /tests/test_verifier_regressions.py
cp /tests/results.json /logs/verifier/results.json
