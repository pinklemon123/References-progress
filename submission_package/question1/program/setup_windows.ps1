$ErrorActionPreference = "Stop"
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe -c "import numpy,pandas,scipy,sklearn,openpyxl; print('Environment OK')"
Write-Host "Run: .\.venv\Scripts\python.exe run.py --mode reproduce"
