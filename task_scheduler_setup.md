# Windows Task Scheduler Setup Instructions

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
