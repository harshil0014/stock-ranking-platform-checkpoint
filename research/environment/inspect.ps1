$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$mainPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $mainPython -PathType Leaf)) {
    throw "Main project interpreter not found: $mainPython"
}
& $mainPython -m stock_research.cli environment-inspect `
    --output (Join-Path $projectRoot "research\generated\environment-status.json")
exit $LASTEXITCODE
