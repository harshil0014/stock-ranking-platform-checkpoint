param(
    [switch]$FullBackfill,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Python = Join-Path $ProjectRoot '.venv-marketdata\Scripts\python.exe'
$Runner = Join-Path $ProjectRoot 'marketdata\runners\refresh_company_data.py'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Missing isolated market-data interpreter: $Python"
}
$Arguments = @($Runner)
if ($FullBackfill) { $Arguments += '--full-backfill' }
if ($DryRun) { $Arguments += '--dry-run' }
& $Python @Arguments
exit $LASTEXITCODE
