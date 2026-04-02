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

$Action  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$BatFile`""
$Trigger = New-ScheduledTaskTrigger -Daily -At $StartTime
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

# Repeat every 8 hours within the day
$Trigger.RepetitionInterval = [System.TimeSpan]::FromHours($IntervalHr)
$Trigger.RepetitionDuration = [System.TimeSpan]::FromHours(24)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -RunLevel Limited `
    -Description "Automated job scraper -- runs every $IntervalHr hours"

Write-Host ""
Write-Host "Task '$TaskName' registered successfully."
Write-Host "Schedule: daily at $StartTime, repeating every $IntervalHr hours."
Write-Host ""
Write-Host "To run it immediately:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "To check status:        Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "To remove it:           Unregister-ScheduledTask -TaskName '$TaskName'"
