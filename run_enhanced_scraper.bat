@echo off
echo ========================================
echo Enhanced Job Scraper V2 - Starting...
echo ========================================
cd /d "%~dp0"

REM Check Python availability
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found or not in PATH
    echo Please install Python and add it to your PATH
    pause
    exit /b 1
)

echo Python detected successfully
echo.

REM Check if enhanced config exists
if not exist "config.json" (
    if exist "config_enhanced.json" (
        echo Using enhanced configuration...
        copy config_enhanced.json config.json
    )
)

echo Running Enhanced Job Scraper V2...
echo - Software Engineering roles ONLY
echo - Israeli locations ONLY  
echo - Individual job page crawling ENABLED
echo.

REM Run the enhanced scraper
python job_scraper_v2_enhanced.py

REM Check results
if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo SUCCESS: Job scraping completed!
    echo ========================================
    echo Check job_postings.xlsx for results
    echo Check logs folder for detailed logs
) else (
    echo.
    echo ========================================
    echo ERROR: Job scraper encountered issues
    echo ========================================
    echo Check the logs for details:
    echo logs\job_scraper_%date:~10,4%%date:~4,2%%date:~7,2%.log
)

echo.
pause
