param([switch]$DryRun)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Python = Join-Path $ProjectRoot '.venv-marketdata\Scripts\python.exe'
$Runner = Join-Path $ProjectRoot 'marketdata\runners\discover_pit_fundamental_scale.py'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Missing isolated market-data interpreter: $Python"
}
$Stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$Output = Join-Path $ProjectRoot "data\marketdata\pit-fundamental-discovery-$Stamp"
$Arguments = @($Runner, '--output', $Output)
if ($DryRun) {
    [ordered]@{
        write_free = $true
        command = @($Python) + $Arguments
        behavior = 'Official NSE metadata-only discovery; no PDF download and no Research V2 promotion.'
    } | ConvertTo-Json -Depth 4
    exit 0
}
& $Python @Arguments
exit $LASTEXITCODE
