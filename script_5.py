# Create an enhanced version of the job scraper with better features
enhanced_scraper = '''
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import json
import time
import hashlib
import logging
from datetime import datetime
import os
import re
from urllib.parse import urljoin, urlparse
import ollama
from pathlib import Path

class JobScraper:
    def __init__(self, config_file='config.json'):
        """Initialize the job scraper with configuration"""
        self.config = self.load_config(config_file)
        self.setup_logging()
        self.existing_jobs = self.load_existing_jobs()
        self.session = requests.Session()
        self.setup_session()
        
    def load_config(self, config_file):
        """Load configuration from JSON file"""
        default_config = {
            "excel_file": "job_postings.xlsx",
            "urls_file": "company_urls.txt",
            "ollama_model": "llama3.2",
            "max_retries": 3,
            "delay_between_requests": 2,
            "timeout": 30,
            "use_selenium_for_js": True,
            "headless_browser": True,
            "log_level": "INFO",
            "max_jobs_per_site": 50,
            "content_length_limit": 8000
        }
        
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                user_config = json.load(f)
                default_config.update(user_config)
        else:
            # Create default config file
            with open(config_file, 'w') as f:
                json.dump(default_config, f, indent=4)
                
        return default_config
    
    def setup_session(self):
        """Setup requests session with headers and retry strategy"""
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        })
    
    def setup_logging(self):
        """Setup logging configuration"""
        # Create logs directory if it doesn't exist
        logs_dir = Path('logs')
        logs_dir.mkdir(exist_ok=True)
        
        log_file = logs_dir / f'job_scraper_{datetime.now().strftime("%Y%m%d")}.log'
        
        logging.basicConfig(
            level=getattr(logging, self.config['log_level']),
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def load_existing_jobs(self):
        """Load existing jobs from Excel file to avoid duplicates"""
        existing_jobs = set()
        excel_file = self.config['excel_file']
        
        if os.path.exists(excel_file):
            try:
                df = pd.read_excel(excel_file)
                if not df.empty:
                    # Create unique identifiers based on title, company, and location
                    for _, row in df.iterrows():
                        job_id = self.create_job_id(
                            str(row.get('Title', '')), 
                            str(row.get('Company', '')), 
                            str(row.get('Location', ''))
                        )
                        existing_jobs.add(job_id)
                self.logger.info(f"Loaded {len(existing_jobs)} existing job postings")
            except Exception as e:
                self.logger.error(f"Error loading existing jobs: {e}")
                
        return existing_jobs
    
    def create_job_id(self, title, company, location):
        """Create a unique identifier for a job posting"""
        job_string = f"{title}_{company}_{location}".lower().strip()
        job_string = re.sub(r'[^a-zA-Z0-9_]', '', job_string)  # Remove special characters
        return hashlib.md5(job_string.encode()).hexdigest()
    
    def load_company_urls(self):
        """Load company URLs from text file"""
        urls = []
        urls_file = self.config['urls_file']
        
        if not os.path.exists(urls_file):
            # Create sample URLs file
            sample_urls = [
                "# Company Career Page URLs",
                "# Add one URL per line, lines starting with # are ignored",
                "",
                "# Example URLs (replace with actual company career pages):",
                "https://careers.microsoft.com/professionals/us/en/search-results",
                "https://careers.google.com/jobs/results/",
                "https://jobs.netflix.com/jobs",
                "https://www.amazon.jobs/en/search",
                "https://careers.apple.com/us/search",
                "",
                "# Add your target company URLs here:",
                "# https://company1.com/careers",
                "# https://company2.com/jobs",
                "# https://company3.com/careers",
                "",
                "# Tips:",
                "# - Use the main careers/jobs page URL, not specific job posting URLs",
                "# - Some companies may require JavaScript (Selenium will handle these)",
                "# - Test URLs manually first to ensure they load properly"
            ]
            with open(urls_file, 'w') as f:
                f.write('\\n'.join(sample_urls))
            self.logger.info(f"Created sample URLs file: {urls_file}")
            
        with open(urls_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    urls.append(line)
                    
        self.logger.info(f"Loaded {len(urls)} URLs to scrape")
        return urls
    
    def scrape_with_requests(self, url):
        """Scrape website using requests and BeautifulSoup"""
        for attempt in range(self.config['max_retries']):
            try:
                response = self.session.get(url, timeout=self.config['timeout'])
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.decompose()
                
                text = soup.get_text(separator=' ', strip=True)
                
                # Clean up whitespace
                text = re.sub(r'\\s+', ' ', text)
                
                self.logger.info(f"Successfully scraped {url} with requests (attempt {attempt + 1})")
                return text
                
            except requests.RequestException as e:
                self.logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt < self.config['max_retries'] - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                continue
                
        self.logger.error(f"All attempts failed for {url}")
        return None
    
    def scrape_with_selenium(self, url):
        """Scrape JavaScript-heavy websites using Selenium"""
        driver = None
        for attempt in range(self.config['max_retries']):
            try:
                chrome_options = Options()
                if self.config['headless_browser']:
                    chrome_options.add_argument("--headless")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--window-size=1920,1080")
                chrome_options.add_argument("--disable-blink-features=AutomationControlled")
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                
                # Use WebDriver Manager to handle ChromeDriver automatically
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
                
                # Execute script to remove webdriver property
                driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                
                driver.get(url)
                
                # Wait for page to load
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                # Additional wait for dynamic content
                time.sleep(5)
                
                # Try to scroll to load more content
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                time.sleep(2)
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)
                
                page_text = driver.find_element(By.TAG_NAME, "body").text
                
                self.logger.info(f"Successfully scraped {url} with Selenium (attempt {attempt + 1})")
                return page_text
                
            except Exception as e:
                self.logger.warning(f"Selenium attempt {attempt + 1} failed for {url}: {e}")
                if attempt < self.config['max_retries'] - 1:
                    time.sleep(3 * (attempt + 1))
                continue
            finally:
                if driver:
                    driver.quit()
                    
        self.logger.error(f"All Selenium attempts failed for {url}")
        return None
    
    def extract_company_name_from_url(self, url):
        """Extract company name from URL"""
        try:
            domain = urlparse(url).netloc.lower()
            # Remove www. and common suffixes
            domain = domain.replace('www.', '').replace('careers.', '').replace('jobs.', '')
            company = domain.split('.')[0]
            
            # Handle special cases
            company_mapping = {
                'amazon': 'Amazon',
                'google': 'Google',
                'microsoft': 'Microsoft',
                'apple': 'Apple',
                'netflix': 'Netflix',
                'meta': 'Meta',
                'facebook': 'Meta',
                'linkedin': 'LinkedIn',
                'salesforce': 'Salesforce'
            }
            
            return company_mapping.get(company, company.title())
        except:
            return "Unknown Company"
    
    def analyze_with_ollama(self, scraped_content, company_url):
        """Use Ollama to analyze scraped content and extract job information"""
        company_name = self.extract_company_name_from_url(company_url)
        
        # Limit content length to avoid token limits
        content_limit = self.config.get('content_length_limit', 8000)
        limited_content = scraped_content[:content_limit]
        
        prompt = f"""
        Analyze the following scraped content from {company_name}'s career page and extract job postings.
        Look for job titles, locations, descriptions, and qualifications.
        
        Return ONLY a valid JSON object in this exact format:
        {{
            "jobs": [
                {{
                    "title": "Software Engineer",
                    "location": "San Francisco, CA",
                    "description": "Build scalable web applications using modern technologies",
                    "qualifications": "Bachelor's degree, 3+ years Python experience, knowledge of React",
                    "url": "{company_url}"
                }}
            ]
        }}
        
        Rules:
        - Extract only actual job postings, not general career information
        - If no jobs found, return {{"jobs": []}}
        - Keep descriptions concise (1-2 sentences)
        - Extract key qualifications only
        - Use "Remote" if job is remote work
        - Maximum {self.config.get('max_jobs_per_site', 50)} jobs per response
        
        Content to analyze:
        {limited_content}
        """
        
        try:
            self.logger.info(f"Analyzing content with Ollama for {company_name}")
            response = ollama.chat(
                model=self.config['ollama_model'],
                messages=[{'role': 'user', 'content': prompt}]
            )
            
            response_text = response['message']['content'].strip()
            
            # Find JSON in the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                try:
                    job_data = json.loads(json_str)
                    jobs = job_data.get('jobs', [])
                    
                    # Add company name and validate data
                    validated_jobs = []
                    for job in jobs:
                        if job.get('title') and job.get('location'):
                            job['company'] = company_name
                            if not job.get('url') or job['url'] == company_url:
                                job['url'] = company_url
                            validated_jobs.append(job)
                    
                    self.logger.info(f"Extracted {len(validated_jobs)} jobs from {company_name}")
                    return validated_jobs
                    
                except json.JSONDecodeError as e:
                    self.logger.error(f"JSON decode error for {company_url}: {e}")
                    return []
            else:
                self.logger.error(f"No valid JSON found in Ollama response for {company_url}")
                return []
                
        except Exception as e:
            self.logger.error(f"Error analyzing content with Ollama for {company_url}: {e}")
            return []
    
    def scrape_company_jobs(self, url):
        """Scrape jobs from a single company URL"""
        self.logger.info(f"Scraping jobs from: {url}")
        
        # Try requests first, then Selenium if needed
        scraped_content = self.scrape_with_requests(url)
        
        if not scraped_content and self.config['use_selenium_for_js']:
            self.logger.info(f"Trying Selenium for {url}")
            scraped_content = self.scrape_with_selenium(url)
        
        if not scraped_content:
            self.logger.warning(f"No content scraped from {url}")
            return []
        
        # Log content length for debugging
        self.logger.debug(f"Scraped {len(scraped_content)} characters from {url}")
        
        # Analyze content with Ollama
        jobs = self.analyze_with_ollama(scraped_content, url)
        
        # Filter out duplicates and validate
        new_jobs = []
        for job in jobs:
            # Ensure required fields exist
            if not all([job.get('title'), job.get('company'), job.get('location')]):
                continue
                
            job_id = self.create_job_id(job['title'], job['company'], job['location'])
            if job_id not in self.existing_jobs:
                job['date_added'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                # Ensure all required fields have default values
                job.setdefault('description', 'No description available')
                job.setdefault('qualifications', 'No qualifications specified')
                job.setdefault('url', url)
                
                new_jobs.append(job)
                self.existing_jobs.add(job_id)
            else:
                self.logger.debug(f"Duplicate job skipped: {job['title']} at {job['company']}")
        
        self.logger.info(f"Found {len(new_jobs)} new jobs from {url}")
        return new_jobs
    
    def save_jobs_to_excel(self, all_jobs):
        """Save jobs to Excel file"""
        if not all_jobs:
            self.logger.info("No new jobs to save")
            return
        
        try:
            # Convert to DataFrame
            df_new = pd.DataFrame(all_jobs)
            
            # Reorder columns
            column_order = ['date_added', 'title', 'url', 'company', 'description', 'qualifications', 'location']
            df_new = df_new.reindex(columns=column_order)
            
            # Rename columns for Excel
            df_new.columns = ['Date Added', 'Title', 'URL', 'Company', 'Description', 'Qualifications', 'Location']
            
            excel_file = self.config['excel_file']
            
            # Create backup of existing file
            if os.path.exists(excel_file):
                backup_file = f"{excel_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                import shutil
                shutil.copy2(excel_file, backup_file)
                
                df_existing = pd.read_excel(excel_file)
                df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            else:
                df_combined = df_new
            
            # Save to Excel with formatting
            with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
                df_combined.to_excel(writer, index=False, sheet_name='Job Postings')
                
                # Auto-adjust column widths
                workbook = writer.book
                worksheet = writer.sheets['Job Postings']
                
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
            
            self.logger.info(f"Saved {len(all_jobs)} new jobs to {excel_file}")
            
        except Exception as e:
            self.logger.error(f"Error saving jobs to Excel: {e}")
    
    def run(self):
        """Main execution method"""
        start_time = datetime.now()
        self.logger.info(f"Starting job scraping session at {start_time}")
        
        # Load URLs
        company_urls = self.load_company_urls()
        
        if not company_urls:
            self.logger.error("No URLs to scrape. Please add URLs to company_urls.txt")
            return
        
        all_new_jobs = []
        successful_scrapes = 0
        failed_scrapes = 0
        
        for i, url in enumerate(company_urls, 1):
            try:
                self.logger.info(f"Processing {i}/{len(company_urls)}: {url}")
                jobs = self.scrape_company_jobs(url)
                all_new_jobs.extend(jobs)
                
                if jobs:
                    successful_scrapes += 1
                else:
                    failed_scrapes += 1
                
                # Delay between requests
                if i < len(company_urls):  # Don't delay after last URL
                    time.sleep(self.config['delay_between_requests'])
                
            except Exception as e:
                self.logger.error(f"Error processing {url}: {e}")
                failed_scrapes += 1
                continue
        
        # Save all jobs to Excel
        self.save_jobs_to_excel(all_new_jobs)
        
        # Summary
        end_time = datetime.now()
        duration = end_time - start_time
        
        self.logger.info("="*50)
        self.logger.info("JOB SCRAPING SESSION COMPLETE")
        self.logger.info("="*50)
        self.logger.info(f"Duration: {duration}")
        self.logger.info(f"URLs processed: {len(company_urls)}")
        self.logger.info(f"Successful scrapes: {successful_scrapes}")
        self.logger.info(f"Failed scrapes: {failed_scrapes}")
        self.logger.info(f"New jobs found: {len(all_new_jobs)}")
        self.logger.info(f"Total existing jobs: {len(self.existing_jobs)}")
        self.logger.info("="*50)

def main():
    """Main entry point"""
    try:
        scraper = JobScraper()
        scraper.run()
    except KeyboardInterrupt:
        logging.info("Job scraper interrupted by user")
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    main()
'''

# Save the enhanced script
with open('job_scraper_enhanced.py', 'w') as f:
    f.write(enhanced_scraper)

print("Created job_scraper_enhanced.py - Enhanced version with better error handling and features")