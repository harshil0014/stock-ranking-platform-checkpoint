param(
    [string]$TaskName = 'StockRankingPlatform-WeeklyFundamentalDiscovery',
    [string]$At = '20:30',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$DiscoveryScript = (Resolve-Path (Join-Path $PSScriptRoot 'windows_fundamental_discovery.ps1')).Path
$PowerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
if ($At -notmatch '^([01]\d|2[0-3]):[0-5]\d$') { throw 'At must use 24-hour HH:mm format.' }
$ActionArguments = "-NoProfile -ExecutionPolicy Bypass -File `"$DiscoveryScript`""
$Plan = [ordered]@{
    task_name = $TaskName
    schedule = "Every Monday at $At Asia/Kolkata local machine time"
    executable = $PowerShell
    arguments = $ActionArguments
    working_directory = $ProjectRoot
    behavior = 'Metadata-only PIT filing discovery; evidence review and promotion remain separate.'
}
if ($DryRun) { $Plan | ConvertTo-Json -Depth 4; exit 0 }
$Action = New-ScheduledTaskAction -Execute $PowerShell -Argument $ActionArguments -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday -At $At
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 4)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description 'Official annual-report metadata discovery without automatic V2 promotion.' -Force | Out-Null
$Info = Get-ScheduledTaskInfo -TaskName $TaskName
$Plan.status = (Get-ScheduledTask -TaskName $TaskName).State.ToString()
$Plan.next_run_time = if ($Info.NextRunTime) { $Info.NextRunTime.ToString('o') } else { $null }
$Plan | ConvertTo-Json -Depth 4
