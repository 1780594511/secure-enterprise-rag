param([string]$Python = 'py')
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    if (!(Test-Path '.venv/Scripts/python.exe')) {
        if ($Python -eq 'py') { & py -3.12 -m venv .venv } else { & $Python -m venv .venv }
        if ($LASTEXITCODE) { throw 'Could not create the Python 3.12 environment.' }
    }
    & ./.venv/Scripts/python.exe -m pip install -r requirements.lock
    if ($LASTEXITCODE) { throw 'Python dependency installation failed.' }
    Push-Location frontend
    try {
        & npm.cmd ci
        if ($LASTEXITCODE) { throw 'npm ci failed.' }
        & npm.cmd run build
        if ($LASTEXITCODE) { throw 'UI build failed.' }
    } finally { Pop-Location }
} finally { Pop-Location }

