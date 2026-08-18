#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -c "import numpy,pandas,scipy,sklearn,openpyxl; print('Environment OK')"
echo "Run: .venv/bin/python run.py --mode reproduce"
