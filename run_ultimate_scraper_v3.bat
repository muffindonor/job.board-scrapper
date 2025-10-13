@echo off
echo ==========================================
echo Ultimate Job Scraper V3 - Starting...
echo ==========================================
echo.

REM Check environment
if "%GOOGLE_SHEETS_CREDS%"=="" (
    echo ERROR: GOOGLE_SHEETS_CREDS environment variable not set
    echo Please run: set GOOGLE_SHEETS_CREDS=path\to\credentials.json
    echo.
    pause
    exit /b 1
)

echo Google Sheets credentials: %GOOGLE_SHEETS_CREDS%
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found
    pause
    exit /b 1
)

echo Python detected successfully
echo.

REM Use V3 config if available
if exist "config_v3.json" (
    if not exist "config.json" (
        copy config_v3.json config.json
        echo Using V3 configuration...
    )
)

echo Running Ultimate Job Scraper V3...
echo - WebGL spam eliminated
echo - NVIDIA jobs issue fixed  
echo - Google Sheets integration (Sheet2)
echo - Enhanced formatting and filtering
echo.

REM Run V3 scraper
python job_scraper_v3_ultimate.py

if %errorlevel% equ 0 (
    echo.
    echo ==========================================
    echo SUCCESS: Job scraping completed!
    echo ==========================================
    echo Check your Google Sheet (Sheet2) for results
) else (
    echo.
    echo ==========================================
    echo ERROR: Check the logs for details
    echo ==========================================
)

echo.
pause
