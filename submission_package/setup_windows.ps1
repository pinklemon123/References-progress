$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
    if ($LASTEXITCODE -ne 0) {
        & py -0p
        if ($LASTEXITCODE -ne 0) {
            & py list
        }
        throw "默认 Python 低于 3.10。请按运行说明选择 py -3.10、-3.11、-3.12 或 -3.13。"
    }
    & py -m venv .venv
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "需要 Python 3.10 或更高版本。"
    }
    & python -m venv .venv
}
else {
    throw "未检测到 Python。请先安装 Python 3.10 或更高版本。"
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe reproduce_all.py
