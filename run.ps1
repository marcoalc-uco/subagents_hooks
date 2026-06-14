# Bootstrap + test: creates .venv if missing, installs deps, runs pytest.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "Creating .venv..."
    python -m venv (Join-Path $root ".venv")
    & $python -m pip install --quiet --upgrade pip
    & $python -m pip install --quiet -r (Join-Path $root "requirements.txt")
}

& $python -m pytest (Join-Path $root "tests") -v
& agent-evals init sandbox_scaffold/
exit $LASTEXITCODE
