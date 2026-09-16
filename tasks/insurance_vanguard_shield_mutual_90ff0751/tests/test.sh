#!/bin/bash
set -euo pipefail
python -c 'import openpyxl, pdfplumber, pypdf, reportlab, docx'
python /tests/test_sop_verifier.py -q || exit 1
python /tests/sop_verifier.py
cp /tests/results.json /logs/verifier/results.json
