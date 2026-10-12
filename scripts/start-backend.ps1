param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
$rfRoot = Split-Path -Parent $PSScriptRoot
$rfPython = Join-Path $rfRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $rfPython -PathType Leaf)) {
    throw 'Missing .venv. Follow the first-install instructions in README.md.'
}
Push-Location $rfRoot
try {
    & $rfPython -c "import sys, fastapi, pydantic, pydantic_core; print('Python', sys.version.split()[0], '| Pydantic', pydantic.__version__)"
    if ($LASTEXITCODE -ne 0) {
        throw 'Dependency import failed. Do not recreate an existing .venv with another Python. See README.md for environment repair.'
    }
    & $rfPython -m uvicorn ruleforge.api:create_app --factory --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "Backend exited with code $LASTEXITCODE. Inspect the error above."
    }
} finally {
    Pop-Location
}
