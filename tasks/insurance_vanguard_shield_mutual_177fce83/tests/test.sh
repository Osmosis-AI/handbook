#!/bin/bash
set -euo pipefail
set -euo pipefail

python -c 'import openpyxl, pdfplumber, pypdf, reportlab, docx'
python /tests/test_hiroshi_date_range_verifier.py
python /tests/test_carlos_daily_cap_verifier.py
python /tests/test_slack_artifact_path_verifier.py
python /tests/test_hassan_rahimi_format_verifier.py
python /tests/sop_verifier.py
cp /tests/results.json /logs/verifier/results.json
