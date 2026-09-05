param(
    [string]$TaskName = 'StockRankingPlatform-WeekdayRefresh',
    [string]$At = '20:00',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$RefreshScript = (Resolve-Path (Join-Path $PSScriptRoot 'windows_refresh.ps1')).Path
$PowerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
if ($At -notmatch '^([01]\d|2[0-3]):[0-5]\d$') {
    throw 'At must use 24-hour HH:mm format.'
}
$ActionArguments = "-NoProfile -ExecutionPolicy Bypass -File `"$RefreshScript`""
$Description = 'Offline-first Indian equity refresh; validated atomic promotion with last-known-good retention.'
$Plan = [ordered]@{
    task_name = $TaskName
    schedule = "Monday-Friday at $At Asia/Kolkata local machine time"
    executable = $PowerShell
    arguments = $ActionArguments
    working_directory = $ProjectRoot
    refresh_script = $RefreshScript
    scientific_models = 'UNCHANGED'
}
if ($DryRun) {
    $Plan | ConvertTo-Json -Depth 4
    exit 0
}
$Action = New-ScheduledTaskAction -Execute $PowerShell -Argument $ActionArguments -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $At
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 8)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description $Description -Force | Out-Null
$Task = Get-ScheduledTask -TaskName $TaskName
$Info = Get-ScheduledTaskInfo -TaskName $TaskName
$Plan.status = $Task.State.ToString()
$Plan.next_run_time = if ($Info.NextRunTime) { $Info.NextRunTime.ToString('o') } else { $null }
$Plan | ConvertTo-Json -Depth 4
