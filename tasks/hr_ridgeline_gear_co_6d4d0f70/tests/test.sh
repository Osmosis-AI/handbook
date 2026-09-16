#!/bin/bash
set -euo pipefail
set -euo pipefail

python -c 'import openpyxl, pdfplumber, pypdf, reportlab, docx'
python -m unittest discover -s /tests -p 'test_*.py'
python /tests/sop_verifier.py
cp /tests/results.json /logs/verifier/results.json
