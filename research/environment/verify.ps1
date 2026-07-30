$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$environmentPython = Join-Path $projectRoot ".venv-qlib\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $environmentPython -PathType Leaf)) {
    Write-Error "Qlib environment does not exist."
    exit 3
}
$outputDirectory = Join-Path $projectRoot "research\generated"
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
$lockPath = Join-Path $outputDirectory "qlib-pip-freeze.txt"
& $environmentPython -m pip freeze | Set-Content -LiteralPath $lockPath -Encoding utf8
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $environmentPython (Join-Path $PSScriptRoot "verify_environment.py") `
    --lock $lockPath `
    --output (Join-Path $outputDirectory "qlib-environment-verified.json")
exit $LASTEXITCODE
