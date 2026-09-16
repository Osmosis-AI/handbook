#!/bin/bash
set -euo pipefail
python -c 'import openpyxl, pdfplumber, pypdf, reportlab, docx'
python /tests/test_closure_date_verifier.py
python /tests/test_famli_referral.py
python /tests/test_non_applicability_verifier.py
python /tests/test_fresh_rca_regressions.py
python /tests/sop_verifier.py
cp /tests/results.json /logs/verifier/results.json
