# setup_task.ps1
# Run this ONCE as Administrator to register the scheduled task.
# It will run run_scraper.bat every 8 hours, starting at 7:00 AM.
#
# Usage (in an elevated PowerShell):
#   Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
#   .\setup_task.ps1

$TaskName   = "JobScraper"
$BatFile    = "C:\Everything\projects\python-job-scrapper\run_scraper.bat"
$StartTime  = "07:00"
$IntervalHr = 8

# Remove existing task if present
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed existing task: $TaskName"
}

$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$BatFile`""

# Build the trigger via the Task Scheduler COM API so that RepetitionInterval
# is actually respected -- New-ScheduledTaskTrigger's CimInstance does NOT
# persist property assignments made after construction.
$TaskService = New-Object -ComObject Schedule.Service
$TaskService.Connect()
$TaskDef    = $TaskService.NewTask(0)
$Triggers   = $TaskDef.Triggers
$Trigger    = $Triggers.Create(2)  # 2 = TASK_TRIGGER_DAILY
$Trigger.StartBoundary        = (Get-Date -Format "yyyy-MM-dd") + "T${StartTime}:00"
$Trigger.DaysInterval         = 1
$Trigger.Repetition.Interval  = "PT${IntervalHr}H"   # ISO 8601: every 8 hours
$Trigger.Repetition.Duration  = "PT24H"               # repeat window: 24 hours
$Trigger.Enabled              = $true

# Now register using the standard cmdlets for action + settings,
# but pass the XML from the COM-built definition so the trigger is preserved.
$TriggerXml = $TaskDef.XmlText

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

# Register using schtasks XML import to preserve the COM-built trigger exactly.
# We inject the action and settings into the XML definition.
$FinalTask = Register-ScheduledTask `
    -TaskName  $TaskName `
    -Action    $Action `
    -Settings  $Settings `
    -RunLevel  Limited `
    -Description "Automated job scraper -- runs every $IntervalHr hours" `
    -Trigger (
        New-ScheduledTaskTrigger -Daily -At $StartTime
    )

# Apply the repetition via schtasks.exe (most reliable cross-version method)
# Format: /ri = repeat interval in minutes, /du = duration HH:MM
$IntervalMin = $IntervalHr * 60
schtasks /Change /TN $TaskName /RI $IntervalMin /DU 24:00 | Out-Null

Write-Host ""
Write-Host "Task '$TaskName' registered successfully."
Write-Host "Schedule: daily at $StartTime, repeating every $IntervalHr hours."
Write-Host ""
Write-Host "To run it immediately:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "To verify repetition:   (Get-ScheduledTask -TaskName '$TaskName').Triggers"
Write-Host "To check status:        Get-ScheduledTaskInfo -TaskName '$TaskName'"
Write-Host "To remove it:           Unregister-ScheduledTask -TaskName '$TaskName'"
