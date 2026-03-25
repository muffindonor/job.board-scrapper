@echo off
:: run_scraper.bat
:: Launches the job scraper inside the project virtualenv.
:: Used by Windows Task Scheduler -- do not run this manually, use python job_scraper.py instead.

:: ── Change this to your actual project folder ────────────────────────────────
set PROJECT_DIR=C:\Everything\projects\python-job-scrapper

:: ── Sheet URL or name (edit to match yours) ──────────────────────────────────
set SHEET=https://docs.google.com/spreadsheets/d/1a7EDFL0-uXIdabblw8eecNmpxPUw9mRaJVm76QDw9P8/edit

:: ── Google credentials (edit path if needed) ─────────────────────────────────
set GOOGLE_SHEETS_CREDS=%PROJECT_DIR%\service_account.json

:: ─────────────────────────────────────────────────────────────────────────────
cd /d "%PROJECT_DIR%"

:: Activate virtualenv
call "%PROJECT_DIR%\.venv\Scripts\activate.bat"

:: Log file for this run (appended, not overwritten)
set LOG=%PROJECT_DIR%\logs\scheduler_%date:~10,4%%date:~4,2%%date:~7,2%.log

echo. >> "%LOG%"
echo ============================= >> "%LOG%"
echo Run started: %date% %time% >> "%LOG%"
echo ============================= >> "%LOG%"

:: Run the scraper, pipe output to log
python "%PROJECT_DIR%\job_scraper.py" --sheet "%SHEET%" >> "%LOG%" 2>&1

echo Run finished: %date% %time% >> "%LOG%"
