param([int]$Port = 8781)
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    if (!(Test-Path '.venv/Scripts/python.exe')) { throw 'Run scripts/Install.ps1 first.' }
    if (!(Test-Path 'frontend/dist/index.html')) { throw 'Build the frontend with scripts/Install.ps1 first.' }
    & ./.venv/Scripts/python.exe -m uvicorn rag.main:app --host 127.0.0.1 --port $Port --no-access-log
    exit $LASTEXITCODE
} finally { Pop-Location }

