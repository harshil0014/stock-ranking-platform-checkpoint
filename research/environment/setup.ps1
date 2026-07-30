$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$environmentPath = Join-Path $projectRoot ".venv-qlib"
$requirementsPath = Join-Path $PSScriptRoot "requirements-qlib.txt"
$python312 = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($python312)) {
    Write-Error "python_3_12_missing: Qlib environment remains specified_blocked."
    exit 3
}
if (Test-Path -LiteralPath $environmentPath) {
    Write-Error "Refusing to reuse $environmentPath. Run cleanup.ps1 after validation."
    exit 4
}
& $python312 -m venv $environmentPath
$environmentPython = Join-Path $environmentPath "Scripts\python.exe"
& $environmentPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $environmentPython -m pip install --requirement $requirementsPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "Candidate constraints failed. They were not relaxed."
    exit $LASTEXITCODE
}
& (Join-Path $PSScriptRoot "verify.ps1")
exit $LASTEXITCODE
