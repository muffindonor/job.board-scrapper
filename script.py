# Create V4.3 - Safe, quota-friendly, data-preserving version
v43_safe_scraper = '''
import os
import json
import time
import re
import gspread
import requests
from datetime import datetime
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException
from gspread.exceptions import APIError
import pandas as pd
import hashlib
import logging
from pathlib import Path
import warnings
import ollama
from typing import List, Dict, Optional, Set, Tuple
import sys

class JobScraperV43Safe:
    def __init__(self, config_file='config.json'):
        """Job scraper V4.3 - SAFE, quota-friendly, data-preserving version"""
        self.config = self.load_config(config_file)
        self.setup_logging()
        self.existing_jobs = set()
        self.session = requests.Session()
        self.setup_session()
        self.setup_filters()
        self.current_year = datetime.now().year
        
        # Ollama check
        if not self.startup_ollama_check():
            self.logger.error("💥 STOPPING: Cannot proceed without Ollama")
            sys.exit(1)
        
        self.setup_google_sheets()
        warnings.filterwarnings("ignore")
        
    def startup_ollama_check(self) -> bool:
        """Check Ollama connection at startup"""
        try:
            self.logger.info("🤖 Testing Ollama connection...")
            test_response = ollama.chat(
                model=self.config['ollama_model'],
                messages=[{'role': 'user', 'content': 'test'}]
            )
            self.logger.info(f"✅ Ollama ({self.config['ollama_model']}) ready")
            return True
        except Exception as e:
            self.logger.error("❌ OLLAMA CONNECTION FAILED!")
            self.logger.error(f"Error: {e}")
            self.logger.error("🚑 SOLUTION:")
            self.logger.error("  1. Start Ollama: ollama serve")
            self.logger.error(f"  2. Pull model: ollama pull {self.config['ollama_model']}")
            return False
        
    def setup_google_sheets(self):
        """Initialize Google Sheets connection"""
        try:
            creds_path = os.getenv('GOOGLE_SHEETS_CREDS')
            if not creds_path:
                self.logger.error("❌ GOOGLE_SHEETS_CREDS environment variable not set!")
                return
                
            self.gc = gspread.service_account(creds_path)
            self.sheet_name = self.config.get('sheet_name', 'job-scrapper')
            self.logger.info(f"✅ Google Sheets connected: {self.sheet_name}")
        except Exception as e:
            self.logger.error(f"❌ Google Sheets setup failed: {e}")
            self.gc = None
        
    def get_or_create_worksheet_safe(self, sheet_name: str):
        """SAFE worksheet access - NEVER clears existing data"""
        try:
            spreadsheet = self.gc.open(self.sheet_name)
            
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
                self.logger.info(f"✅ Found existing {sheet_name}")
                return worksheet
            except gspread.exceptions.WorksheetNotFound:
                # Only create if doesn't exist - NEVER modify existing
                worksheet = spreadsheet.add_worksheet(sheet_name, 1000, 10)
                headers = ['Title', 'Company', 'Date Posted', 'Description', 'Qualifications', 'Location', 'URL', 'Date Added']
                worksheet.append_row(headers)
                self.logger.info(f"✅ Created new {sheet_name}")
                return worksheet
            
        except Exception as e:
            self.logger.error(f"❌ Error accessing {sheet_name}: {e}")
            return None
    
    def load_existing_jobs_from_sheets(self):
        """Load existing jobs from all sheets"""
        existing_jobs = set()
        
        for sheet_name in ["Sheet2", "Sheet3", "Sheet4"]:
            try:
                worksheet = self.get_or_create_worksheet_safe(sheet_name)
                if not worksheet:
                    continue
                    
                all_values = worksheet.get_all_values()
                if len(all_values) <= 1:
                    continue
                
                for row in all_values[1:]:
                    if len(row) >= 2:  # At least title and company
                        title = row[0] if len(row) > 0 else ''
                        company = row[1] if len(row) > 1 else ''
                        location = row[5] if len(row) > 5 else ''  # Location might be in different position
                        
                        if title and company:
                            job_id = self.create_job_id(title, company, location)
                            existing_jobs.add(job_id)
                            
            except Exception as e:
                self.logger.error(f"❌ Error loading jobs from {sheet_name}: {e}")
        
        self.logger.info(f"📊 Loaded {len(existing_jobs)} existing jobs")
        return existing_jobs
    
    def setup_filters(self):
        """Setup filtering"""
        self.sw_engineering_keywords = {
            "software engineer", "software developer", "developer", "engineer", "programmer",
            "full stack", "fullstack", "frontend", "front-end", "backend", "back-end",
            "web developer", "mobile developer", "ios developer", "android developer",
            "react developer", "angular developer", "vue developer", "node.js developer",
            "python developer", "java developer", ".net developer", "c# developer",
            "javascript developer", "typescript developer", "go developer", "kotlin developer",
            "swift developer", "flutter developer", "react native developer",
            "senior software", "staff software", "principal software", "lead software",
            "technical lead", "tech lead", "engineering lead", "architect",
            "cloud architect", "api developer", "systems engineer", "platform engineer",
            "infrastructure engineer", "site reliability", "sre", "devops engineer",
            "build engineer", "release engineer", "automation engineer", "ci/cd engineer",
            "cloud engineer", "aws engineer", "azure engineer", "gcp engineer",
            "kubernetes engineer", "docker engineer", "qa engineer", "test engineer",
            "automation test", "sdet", "performance engineer", "security engineer",
            "data engineer", "ml engineer", "machine learning engineer", "ai engineer",
            "embedded software", "firmware engineer", "game developer", "blockchain developer"
        }
        
        self.israeli_cities = {
            "jerusalem", "tel aviv", "tel aviv-yafo", "haifa", "petah tikva", "rishon lezion",
            "netanya", "ashdod", "bnei brak", "beersheba", "beer sheva", "holon", "ramat gan",
            "beit shemesh", "ashkelon", "rehovot", "bat yam", "herzliya", "hadera", "kfar saba",
            "modi'in", "modiin", "lod", "givat shmuel", "raanana", "givatayim", "hod hasharon",
            "or yehuda", "yehud", "kiryat", "nazareth", "nahariya", "acre", "akko",
            "tiberias", "eilat", "dimona", "arad", "carmiel", "rosh haayin", "afula",
            "nesher", "caesarea", "karmiel", "safed", "tzfat", "yerushalayim", "hefa"
        }
    
    def load_config(self, config_file):
        """Load configuration"""
        default_config = {
            "sheet_name": "job-scrapper",
            "urls_file": "company_urls.txt",
            "ollama_model": "llama3",
            "max_retries": 3,
            "delay_between_requests": 3,
            "timeout": 30,
            "use_selenium_for_js": True,
            "headless_browser": True,
            "log_level": "INFO",
            "max_jobs_per_site": 30,
            "content_length_limit": 10000,
            "crawl_individual_jobs": True,
            "max_crawl_depth": 5,
            "filter_software_roles_only": True,
            "filter_israel_locations_only": True,
            "verbose_logging": False,
            "enable_job_crawling": True,
            "sheets_batch_size": 10,
            "sheets_write_delay": 6,
            "filter_by_current_year": True
        }
        
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                default_config.update(user_config)
        else:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
                
        return default_config
    
    def setup_session(self):
        """Setup requests session"""
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,he;q=0.8',
            'Accept-Charset': 'utf-8'
        })
    
    def setup_logging(self):
        """Setup logging"""
        logs_dir = Path('logs')
        logs_dir.mkdir(exist_ok=True)
        
        log_file = logs_dir / f'job_scraper_{datetime.now().strftime("%Y%m%d")}.log'
        
        logging.basicConfig(
            level=getattr(logging, self.config['log_level']),
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        for noisy_logger in ['urllib3', 'selenium', 'webdriver_manager', 'requests', 'gspread']:
            logging.getLogger(noisy_logger).setLevel(logging.ERROR)
    
    def create_job_id(self, title, company, location):
        """Create unique job ID"""
        job_string = f"{title}_{company}_{location}".lower().strip()
        job_string = re.sub(r'[^a-zA-Z0-9_]', '', job_string)
        return hashlib.md5(job_string.encode('utf-8')).hexdigest()
    
    def is_software_engineering_role(self, job_title: str) -> bool:
        """Check if job is software engineering role"""
        if not self.config.get('filter_software_roles_only', True):
            return True
            
        title_lower = job_title.lower().strip()
        
        for keyword in self.sw_engineering_keywords:
            if keyword in title_lower:
                return True
        
        if re.search(r'software.*engineer|engineer.*software', title_lower):
            return True
        
        return False
    
    def is_israeli_location(self, location: str) -> bool:
        """STRICT whitelist-only approach"""
        if not self.config.get('filter_israel_locations_only', True):
            return True
            
        if not location or location.strip() == "":
            return False
        
        location_clean = location.strip()
        location_lower = location_clean.lower()
        
        if 'israel' in location_lower or 'ישראל' in location_clean:
            return True
        
        for city in self.israeli_cities:
            if city in location_lower:
                return True
        
        return False
    
    def parse_job_date(self, date_string: str) -> Tuple[bool, str]:
        """Parse job date and validate"""
        if not date_string or date_string.strip() == "":
            return True, "**PDNA**"
        
        year_match = re.search(r'20(\\d{2})', date_string)
        if year_match:
            year = int(f"20{year_match.group(1)}")
            if self.config.get('filter_by_current_year', True):
                if year < self.current_year:
                    return False, ""
            return True, date_string
        
        return True, "**PDNA**"
    
    def is_senior_position(self, title: str) -> bool:
        """Check if position is senior level"""
        title_lower = title.lower()
        return 'senior' in title_lower
    
    def is_student_intern_position(self, title: str) -> bool:
        """Check if position is for students/interns - FIXED REGEX"""
        title_lower = title.lower()
        
        if re.search(r'\\bintern\\b', title_lower):
            return True
        if re.search(r'\\binternship\\b', title_lower):
            return True
        if re.search(r'\\bstudent\\b', title_lower):
            return True
        if re.search(r'\\btrainee\\b', title_lower):
            return True
        if re.search(r'\\bapprentice\\b', title_lower):
            return True
        
        return False
    
    def is_entry_junior_position(self, title: str) -> bool:
        """Check if position is entry/junior level"""
        if self.is_student_intern_position(title):
            return False
        if self.is_senior_position(title):
            return False
            
        title_lower = title.lower()
        entry_keywords = ['entry', 'junior', 'graduate', 'new grad', 'fresh', 'associate']
        return any(keyword in title_lower for keyword in entry_keywords)
    
    def categorize_job(self, title: str) -> str:
        """Categorize job into appropriate sheet"""
        if self.is_senior_position(title):
            return "Sheet4"
        elif self.is_student_intern_position(title):
            return "Sheet2"
        elif self.is_entry_junior_position(title):
            return "Sheet3"
        else:
            return "Sheet3"
    
    def create_silent_chrome_driver(self):
        """Create silent Chrome driver"""
        chrome_options = Options()
        
        if self.config['headless_browser']:
            chrome_options.add_argument("--headless=new")
        
        suppression_args = [
            "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
            "--disable-web-security", "--disable-features=VizDisplayCompositor",
            "--disable-logging", "--disable-extensions", "--log-level=3",
            "--silent", "--disable-webgl", "--disable-webgl2", "--disable-3d-apis"
        ]
        
        for arg in suppression_args:
            chrome_options.add_argument(arg)
        
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            service = Service(ChromeDriverManager().install())
            service.log_path = os.devnull if hasattr(os, 'devnull') else 'NUL'
            driver = webdriver.Chrome(service=service, options=chrome_options)
            return driver
        except Exception as e:
            self.logger.error(f"❌ Chrome driver failed: {e}")
            return None
    
    def load_company_urls(self):
        """Load URLs"""
        urls = []
        urls_file = self.config['urls_file']
        
        if not os.path.exists(urls_file):
            sample_urls = [
                "# Israeli Company Career Pages",
                "https://careers.microsoft.com/professionals/us/en/search-results",
                "https://careers.google.com/jobs/results/"
            ]
            with open(urls_file, 'w', encoding='utf-8') as f:
                f.write('\\n'.join(sample_urls))
            
        with open(urls_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    urls.append(line)
                    
        self.logger.info(f"📋 Loaded {len(urls)} URLs")
        return urls
    
    def scrape_with_requests(self, url):
        """Scrape with requests"""
        for attempt in range(self.config['max_retries']):
            try:
                response = self.session.get(url, timeout=self.config['timeout'])
                response.encoding = 'utf-8'
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.decompose()
                
                text = soup.get_text(separator=' ', strip=True)
                text = re.sub(r'\\s+', ' ', text)
                
                return text, soup
                
            except requests.RequestException:
                if attempt < self.config['max_retries'] - 1:
                    time.sleep(2 ** attempt)
                    continue
        
        return None, None
    
    def scrape_with_selenium(self, url):
        """Scrape with Selenium"""
        driver = self.create_silent_chrome_driver()
        if not driver:
            return None, None
            
        try:
            driver.get(url)
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            time.sleep(3)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            for element in soup(["script", "style", "nav", "footer", "header"]):
                element.decompose()
                
            text = soup.get_text(separator=' ', strip=True)
            text = re.sub(r'\\s+', ' ', text)
            
            return text, soup
            
        except Exception:
            return None, None
        finally:
            if driver:
                driver.quit()
    
    def extract_json_from_llm_response(self, response_text: str) -> Optional[dict]:
        """ROBUST JSON extraction"""
        try:
            response_text = re.sub(r'```json\\s*', '', response_text)
            response_text = re.sub(r'```\\s*', '', response_text)
            
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start == -1 or json_end <= json_start:
                return None
            
            json_str = response_text[json_start:json_end]
            json_str = re.sub(r',\\s*([}\\]])', r'\\1', json_str)
            json_str = re.sub(r'\\n', ' ', json_str)
            
            return json.loads(json_str)
            
        except json.JSONDecodeError:
            return None
    
    def enhanced_ollama_analysis(self, content, company_url):
        """Ollama analysis"""
        company_name = self.extract_company_name_from_url(company_url)
        
        prompt = f"""Extract software engineering jobs from {company_name}.

Rules:
1. ONLY software engineering roles
2. Return VALID JSON only
3. Include date posted if available

Content:
{content[:8000]}

Return ONLY this JSON:
{{
  "jobs": [
    {{
      "title": "Software Engineer",
      "location": "Tel Aviv",
      "description": "Brief summary",
      "qualifications": "Key requirements", 
      "date_posted": "2025-10-17 or empty",
      "url": "{company_url}"
    }}
  ]
}}
"""
        
        try:
            response = ollama.chat(
                model=self.config['ollama_model'],
                messages=[{'role': 'user', 'content': prompt}]
            )
            
            job_data = self.extract_json_from_llm_response(response['message']['content'])
            if not job_data:
                return []
            
            jobs = job_data.get('jobs', [])
            filtered_jobs = []
            
            for job in jobs:
                if not job.get('title'):
                    continue
                
                if not self.is_software_engineering_role(job.get('title', '')):
                    continue
                
                if not self.is_israeli_location(job.get('location', '')):
                    continue
                
                date_valid, formatted_date = self.parse_job_date(job.get('date_posted', ''))
                if not date_valid:
                    continue
                
                job['date_posted'] = formatted_date
                job['company'] = company_name
                job.setdefault('description', 'Description not available')
                job.setdefault('qualifications', 'Qualifications not specified')
                job.setdefault('url', company_url)
                
                filtered_jobs.append(job)
            
            return filtered_jobs
            
        except Exception as e:
            self.logger.error(f"❌ Ollama analysis failed: {e}")
            return []
    
    def scrape_company_jobs(self, url):
        """Scrape jobs"""
        self.logger.info(f"🔍 {urlparse(url).netloc}")
        
        scraped_content, soup = self.scrape_with_requests(url)
        
        if not scraped_content and self.config['use_selenium_for_js']:
            self.logger.info(f"  ↳ Trying Selenium...")
            scraped_content, soup = self.scrape_with_selenium(url)
        
        if not scraped_content:
            self.logger.warning(f"⚠️ Failed to scrape {urlparse(url).netloc}")
            return []
        
        jobs = self.enhanced_ollama_analysis(scraped_content, url)
        
        new_jobs = []
        for job in jobs:
            job_id = self.create_job_id(job['title'], job['company'], job.get('location', ''))
            if job_id not in self.existing_jobs:
                job['date_added'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                new_jobs.append(job)
                self.existing_jobs.add(job_id)
        
        if new_jobs:
            self.logger.info(f"✅ {len(new_jobs)} new jobs")
        
        return new_jobs
    
    def extract_company_name_from_url(self, url):
        """Extract company name"""
        try:
            domain = urlparse(url).netloc.lower()
            domain = domain.replace('www.', '').replace('careers.', '').replace('jobs.', '')
            company = domain.split('.')[0]
            
            mapping = {
                'amazon': 'Amazon', 'google': 'Google', 'microsoft': 'Microsoft',
                'apple': 'Apple', 'nvidia': 'NVIDIA', 'intel': 'Intel'
            }
            
            return mapping.get(company, company.title())
        except:
            return "Unknown"
    
    def write_batch_with_retry(self, worksheet, batch_rows):
        """MINIMAL batch writing - quota-safe"""
        for attempt in range(3):
            try:
                if not batch_rows:
                    return True
                
                worksheet.append_rows(batch_rows)
                return True
                
            except APIError as e:
                if "429" in str(e):
                    self.logger.warning(f"⚠️ Rate limit, waiting...")
                    time.sleep(12)
                    continue
                return False
            except:
                if attempt < 2:
                    time.sleep(6)
                    continue
                return False
        
        return False
    
    def save_jobs_to_sheets(self, all_jobs):
        """Save jobs with MINIMAL operations - quota-safe"""
        if not all_jobs or not self.gc:
            return
        
        # Categorize jobs
        sheet2_jobs = []  # Student/Intern
        sheet3_jobs = []  # Entry/Junior + Regular
        sheet4_jobs = []  # Senior
        
        for job in all_jobs:
            sheet = self.categorize_job(job['title'])
            if sheet == "Sheet2":
                sheet2_jobs.append(job)
            elif sheet == "Sheet3":
                sheet3_jobs.append(job)
            elif sheet == "Sheet4":
                sheet4_jobs.append(job)
        
        # Save to sheets with MINIMAL operations
        if sheet2_jobs:
            self.save_to_sheet_safe("Sheet2", sheet2_jobs, "Student/Intern")
        
        if sheet3_jobs:
            self.save_to_sheet_safe("Sheet3", sheet3_jobs, "Entry/Regular")
        
        if sheet4_jobs:
            self.save_to_sheet_safe("Sheet4", sheet4_jobs, "Senior")
    
    def save_to_sheet_safe(self, sheet_name, jobs, category):
        """SAFE sheet saving - MINIMAL quota usage"""
        try:
            worksheet = self.get_or_create_worksheet_safe(sheet_name)
            if not worksheet:
                return
            
            batch_size = self.config.get('sheets_batch_size', 10)
            delay = self.config.get('sheets_write_delay', 6)
            
            self.logger.info(f"💾 Saving {len(jobs)} {category} jobs to {sheet_name}")
            
            # CORRECT column order - no fancy formatting
            all_rows = []
            for job in jobs:
                row = [
                    job.get('title', ''),                           # Title
                    job.get('company', ''),                         # Company  
                    job.get('date_posted', ''),                     # Date Posted
                    job.get('description', ''),                     # Description
                    job.get('qualifications', ''),                  # Qualifications
                    job.get('location', ''),                        # Location
                    job.get('url', ''),                            # URL
                    job.get('date_added', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))  # Date Added
                ]
                all_rows.append(row)
            
            # Write in batches - MINIMAL operations
            total_batches = (len(all_rows) + batch_size - 1) // batch_size
            successful = 0
            
            for i in range(0, len(all_rows), batch_size):
                batch = all_rows[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                
                self.logger.info(f"  📤 Batch {batch_num}/{total_batches}")
                
                if self.write_batch_with_retry(worksheet, batch):
                    successful += len(batch)
                
                if i + batch_size < len(all_rows):
                    time.sleep(delay)
            
            self.logger.info(f"✅ Saved {successful}/{len(jobs)} to {sheet_name}")
            
        except Exception as e:
            self.logger.error(f"❌ Error saving to {sheet_name}: {e}")
    
    def run(self):
        """Main execution - SAFE version"""
        start_time = datetime.now()
        self.logger.info("🚀 Job Scraper V4.3 - SAFE & QUOTA-FRIENDLY")
        
        if not self.gc:
            self.logger.error("❌ Google Sheets not configured")
            return
        
        self.existing_jobs = self.load_existing_jobs_from_sheets()
        
        urls = self.load_company_urls()
        if not urls:
            self.logger.error("❌ No URLs")
            return
        
        self.logger.info("🛡️ SAFETY FEATURES:")
        self.logger.info("  • NEVER clears existing data")
        self.logger.info("  • MINIMAL API operations") 
        self.logger.info("  • CORRECT column ordering")
        self.logger.info("  • Quota-friendly batch writing")
        
        all_jobs = []
        
        for i, url in enumerate(urls, 1):
            try:
                self.logger.info(f"[{i}/{len(urls)}]")
                jobs = self.scrape_company_jobs(url)
                all_jobs.extend(jobs)
                
                if i < len(urls):
                    time.sleep(self.config['delay_between_requests'])
                
            except Exception as e:
                self.logger.error(f"❌ Error: {e}")
                continue
        
        self.save_jobs_to_sheets(all_jobs)
        
        duration = datetime.now() - start_time
        self.logger.info("=" * 60)
        self.logger.info(f"🎉 COMPLETED SAFELY in {duration}")
        self.logger.info(f"💼 Total jobs: {len(all_jobs)}")
        self.logger.info(f"🛡️ Data preserved, quota respected")
        self.logger.info("=" * 60)

def main():
    try:
        scraper = JobScraperV43Safe()
        scraper.run()
    except KeyboardInterrupt:
        logging.info("⚠️ Interrupted")
    except SystemExit:
        pass
    except Exception as e:
        logging.error(f"💥 Error: {e}")

if __name__ == "__main__":
    main()
'''

with open('job_scraper_v4_3_safe.py', 'w', encoding='utf-8') as f:
    f.write(v43_safe_scraper)

print("🚀 ✅ CREATED job_scraper_v4_3_safe.py")
print()
print("🛡️ V4.3 SAFETY FEATURES:")
print("=" * 25)
print("✅ NEVER clears existing sheets")
print("✅ NEVER overwrites existing data")
print("✅ MINIMAL API operations (no quota issues)")
print("✅ CORRECT column ordering")
print("✅ Batch writing with delays")
print("✅ No fancy formatting (quota killer)")
print("✅ No auto-sorting (quota killer)")
print("✅ Preserves all existing data")
print()
print("🎯 WHAT'S FIXED:")
print("• Column data appears in correct positions")
print("• Timestamp in Date Added for manual sorting")
print("• Safe sheet access (no data deletion)")
print("• Quota-friendly operations only")
print("• Same job detection/filtering quality")
print()
print("▶️ READY TO RUN:")
print("python job_scraper_v4_3_safe.py")
print()
print("💡 Manual sorting tip:")
print("Select your data → Data → Sort range → Date Added column descending")