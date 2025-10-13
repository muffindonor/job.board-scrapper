# Create comprehensive README
readme_content = '''# Automated Job Scraper with LLM Analysis

A Python-based job scraper that automatically monitors company career pages for new job postings using web scraping and Large Language Model (LLM) analysis through Ollama.

## Features

- **Multi-method Scraping**: Uses both requests/BeautifulSoup and Selenium for JavaScript-heavy sites
- **LLM Analysis**: Uses Ollama (llama3.2) to intelligently extract job information from scraped content
- **Duplicate Prevention**: Tracks existing jobs to avoid duplicates
- **Excel Output**: Saves job data to Excel with proper formatting
- **Windows Scheduling**: Easy setup for automated execution via Task Scheduler
- **Comprehensive Logging**: Detailed logs with rotation and error tracking
- **Robust Error Handling**: Retries, backups, and graceful failure handling

## Project Structure

```
job_scraper/
├── job_scraper_enhanced.py    # Main scraping program (recommended)
├── job_scraper.py             # Basic version
├── setup.py                   # Installation and setup script
├── requirements.txt           # Python dependencies
├── config.json               # Configuration settings
├── company_urls.txt          # List of company URLs to scrape
├── run_job_scraper.bat       # Windows batch file for easy execution
├── task_scheduler_setup.md   # Task Scheduler setup instructions
├── logs/                     # Log files directory
├── job_postings.xlsx         # Output Excel file (created after first run)
└── README.md                 # This file
```

## Quick Start

### 1. Prerequisites
- **Python 3.8+** installed and in PATH
- **Google Chrome** browser installed
- **Ollama** installed and running

### 2. Installation
```bash
# Clone or download the project files
# Navigate to the project directory
cd job_scraper

# Run the setup script
python setup.py
```

### 3. Setup Ollama
```bash
# Download and install Ollama from https://ollama.ai/
# After installation, pull the required model:
ollama pull llama3.2

# Verify installation:
ollama list
```

### 4. Configure URLs
Edit `company_urls.txt` and add your target company career page URLs:
```
https://careers.microsoft.com/professionals/us/en/search-results
https://careers.google.com/jobs/results/
https://jobs.netflix.com/jobs
https://your-target-company.com/careers
```

### 5. Test Run
```bash
# Test the scraper manually
python job_scraper_enhanced.py

# Or use the batch file
run_job_scraper.bat
```

### 6. Schedule Automation
Follow the instructions in `task_scheduler_setup.md` to set up automatic execution every few hours.

## Configuration

The `config.json` file allows you to customize the scraper behavior:

```json
{
    "excel_file": "job_postings.xlsx",
    "urls_file": "company_urls.txt",
    "ollama_model": "llama3.2",
    "max_retries": 3,
    "delay_between_requests": 2,
    "timeout": 30,
    "use_selenium_for_js": true,
    "headless_browser": true,
    "log_level": "INFO",
    "max_jobs_per_site": 50,
    "content_length_limit": 8000
}
```

## Output Format

The scraper creates an Excel file with the following columns:
- **Date Added**: When the job was first discovered
- **Title**: Job title
- **URL**: Link to the job posting or career page
- **Company**: Company name (extracted from URL)
- **Description**: Brief job description
- **Qualifications**: Key qualifications and requirements
- **Location**: Job location (city, state, or "Remote")

## How It Works

1. **URL Loading**: Reads company URLs from `company_urls.txt`
2. **Web Scraping**: 
   - Tries requests/BeautifulSoup first (faster)
   - Falls back to Selenium for JavaScript-heavy sites
3. **Content Analysis**: Sends scraped content to Ollama LLM for job extraction
4. **Duplicate Detection**: Compares new jobs against existing ones using hash IDs
5. **Excel Export**: Saves new jobs to Excel with proper formatting
6. **Logging**: Records all activities with timestamps and error details

## Scheduling Options

### Windows Task Scheduler (Recommended)
- Run every 2-4 hours during business hours
- Automatic retry on failure
- Run whether user is logged in or not

### Alternative Methods
- **Cron** (if using WSL): `0 */3 * * * /path/to/run_job_scraper.bat`
- **Python Scheduler**: Use `schedule` library for in-process scheduling
- **GitHub Actions**: For cloud-based execution (requires API keys)

## Troubleshooting

### Common Issues

**Ollama Connection Error**
```
Error: Could not connect to Ollama
Solution: Ensure Ollama service is running (ollama serve)
```

**Chrome Driver Issues**
```
Error: Chrome driver not found
Solution: Update Chrome browser, check firewall settings
```

**No Jobs Found**
```
Issue: LLM returns empty results
Solution: Check if URLs are loading properly, verify content is being scraped
```

**Excel Permission Denied**
```
Issue: Cannot write to Excel file
Solution: Close Excel if open, check file permissions
```

### Debugging Steps

1. **Check Logs**: Review `logs/job_scraper_YYYYMMDD.log`
2. **Test URLs**: Manually visit URLs to ensure they load
3. **Verify Ollama**: Run `ollama list` and `ollama run llama3.2`
4. **Test Browser**: Run with `headless_browser: false` to see what Selenium sees
5. **Reduce Scope**: Test with 1-2 URLs first

## Legal and Ethical Considerations

### Best Practices
- **Respect robots.txt**: Check site policies before scraping
- **Rate Limiting**: Use appropriate delays between requests
- **Personal Use**: This tool is intended for personal job searching
- **Terms of Service**: Review each company's ToS before scraping

### Compliance
- The scraper includes reasonable delays and respectful headers
- It targets public career pages, not private data
- Users are responsible for complying with applicable laws and ToS

## Advanced Usage

### Custom LLM Models
```json
{
    "ollama_model": "mistral",  // or "codellama", "llama2"
}
```

### Multiple Output Formats
```python
# Extend the scraper to output CSV, JSON, or database
def save_to_csv(self, jobs):
    df = pd.DataFrame(jobs)
    df.to_csv('jobs.csv', index=False)
```

### API Integration
```python
# Add webhook notifications or API integrations
def notify_new_jobs(self, jobs):
    # Send to Slack, email, or other services
    pass
```

## Contributing

Improvements and features are welcome:
- Better job extraction prompts for specific companies
- Additional output formats (CSV, JSON, database)
- Integration with job boards that offer APIs
- Enhanced duplicate detection algorithms
- Better error recovery mechanisms

## License

This project is for educational and personal use. Users are responsible for complying with applicable laws and website terms of service.

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review log files for specific errors
3. Test with a minimal configuration
4. Ensure all dependencies are properly installed

## Version History

- **v1.0**: Basic scraping with requests and BeautifulSoup
- **v1.1**: Added Selenium support for JavaScript sites
- **v1.2**: Integrated Ollama for LLM-based job extraction
- **v2.0**: Enhanced version with better error handling, logging, and features
'''

with open('README.md', 'w') as f:
    f.write(readme_content)

print("Created comprehensive README.md")