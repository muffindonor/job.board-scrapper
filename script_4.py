# Create setup script with proper string handling
setup_script = """
import subprocess
import sys
import os

def install_requirements():
    \"\"\"Install required Python packages\"\"\"
    print("Installing required Python packages...")
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
        print("✓ Successfully installed Python packages")
    except subprocess.CalledProcessError as e:
        print(f"✗ Error installing packages: {e}")
        return False
    return True

def setup_ollama():
    \"\"\"Instructions for setting up Ollama\"\"\"
    print("\\n" + "="*50)
    print("OLLAMA SETUP REQUIRED")
    print("="*50)
    print("1. Download and install Ollama from: https://ollama.ai/")
    print("2. After installation, open Command Prompt and run:")
    print("   ollama pull llama3.2")
    print("3. Verify installation by running:")
    print("   ollama list")
    print("4. Make sure Ollama service is running before using the job scraper")
    print("="*50)

def setup_chrome_driver():
    \"\"\"Instructions for Chrome driver setup\"\"\"
    print("\\n" + "="*50)
    print("CHROME DRIVER SETUP")
    print("="*50)
    print("The script uses webdriver-manager to automatically download Chrome driver.")
    print("Make sure you have Google Chrome installed on your system.")
    print("If you encounter issues, you may need to:")
    print("1. Update Google Chrome to the latest version")
    print("2. Check your firewall/antivirus settings")
    print("="*50)

def create_batch_file():
    \"\"\"Create Windows batch file for easy execution\"\"\"
    batch_content = '''@echo off
echo Starting Job Scraper...
cd /d "%~dp0"
python job_scraper.py
pause'''
    
    with open('run_job_scraper.bat', 'w') as f:
        f.write(batch_content)
    print("✓ Created run_job_scraper.bat")

def create_scheduler_instructions():
    \"\"\"Create instructions for Windows Task Scheduler\"\"\"
    instructions = '''# Windows Task Scheduler Setup Instructions

## Automated Job Scraping with Task Scheduler

### Step 1: Open Task Scheduler
1. Press Win + R, type `taskschd.msc`, press Enter
2. Click "Create Basic Task..." in the right panel

### Step 2: Basic Task Configuration
1. **Name**: "Job Scraper"
2. **Description**: "Automated job posting scraper"
3. Click Next

### Step 3: Task Trigger
1. Select "Daily" for daily execution
2. Click Next
3. Set start date and time (e.g., 9:00 AM)
4. Recur every: 1 days
5. Click Next

### Step 4: Action
1. Select "Start a program"
2. Click Next
3. **Program/script**: Browse to `run_job_scraper.bat` file
4. **Start in**: Select the folder containing your job scraper files
5. Click Next

### Step 5: Advanced Settings (Optional)
1. Click "Open the Properties dialog..." before finishing
2. In Security options:
   - Select "Run whether user is logged on or not"
   - Check "Run with highest privileges"
3. In Settings tab:
   - Check "Run task as soon as possible after a scheduled start is missed"
   - Set "If the task fails, restart every: 10 minutes"
   - Set "Attempt to restart up to: 3 times"

### Step 6: Complete Setup
1. Click Finish
2. Enter your Windows password when prompted
3. Test the task by right-clicking and selecting "Run"

## Running Every Few Hours
To run every few hours instead of daily:
1. After creating the task, right-click it and select "Properties"
2. Go to "Triggers" tab, click "Edit"
3. Change to "Daily" and check "Repeat task every: 3 hours"
4. Set duration to "Indefinitely"

## Monitoring
- Check `job_scraper.log` for execution logs
- Check `job_postings.xlsx` for scraped jobs
- Task Scheduler History tab shows execution status

## Troubleshooting
- Ensure Python is in system PATH
- Run the batch file manually first to test
- Check Windows Event Viewer if task fails
- Verify Ollama service is running
'''

    with open('task_scheduler_setup.md', 'w') as f:
        f.write(instructions)
    print("✓ Created task_scheduler_setup.md")

def main():
    print("Job Scraper Setup")
    print("=" * 30)
    
    # Install requirements
    if not install_requirements():
        return
    
    # Create batch file
    create_batch_file()
    
    # Create scheduler instructions
    create_scheduler_instructions()
    
    # Setup instructions
    setup_ollama()
    setup_chrome_driver()
    
    print("\\n" + "="*50)
    print("SETUP COMPLETE!")
    print("="*50)
    print("Next steps:")
    print("1. Install and setup Ollama (see instructions above)")
    print("2. Edit company_urls.txt with your target companies")
    print("3. Test by running: run_job_scraper.bat")
    print("4. Set up Windows Task Scheduler using task_scheduler_setup.md")
    print("="*50)

if __name__ == "__main__":
    main()
"""

with open('setup.py', 'w') as f:
    f.write(setup_script)

print("Created setup.py")