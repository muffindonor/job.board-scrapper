@echo off
echo ==========================================
echo Job Scraper V3.1 - Rate Limited Version
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

REM Use V3.1 config if available
if exist "config_v3_1.json" (
    if not exist "config.json" (
        copy config_v3_1.json config.json
        echo Using V3.1 configuration with rate limiting...
    )
)

echo Running Rate-Limited Job Scraper V3.1...
echo - Fixes Google Sheets quota exceeded errors
echo - Batch processing (10 jobs per batch)
echo - 6 second delays between batches
echo - Guaranteed job saving with retry logic
echo.

REM Run V3.1 scraper
python job_scraper_v3_1_rate_limited.py

if %errorlevel% equ 0 (
    echo.
    echo ==========================================
    echo SUCCESS: All jobs saved successfully!
    echo ==========================================
    echo Check your Google Sheet (Sheet2) for results
    echo No more missing jobs due to quota limits!
) else (
    echo.
    echo ==========================================
    echo ERROR: Check the logs for details
    echo ==========================================
)

echo.
pause
