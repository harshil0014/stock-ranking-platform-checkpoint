$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$expected = Join-Path $projectRoot ".venv-qlib"
if (-not (Test-Path -LiteralPath $expected)) {
    Write-Output "Nothing to remove: $expected"
    exit 0
}
$resolved = (Resolve-Path -LiteralPath $expected).Path
if ($resolved -ne $expected) {
    throw "Unexpected cleanup target: $resolved"
}
Remove-Item -LiteralPath $resolved -Recurse -Force
Write-Output "Removed isolated Qlib environment: $resolved"
