# Create V4.1 with all fixes and new requirements
v4_1_complete = '''
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

class JobScraperV41:
    def __init__(self, config_file='config.json'):
        """Job scraper V4.1 with fail-fast Ollama check and new sheet organization"""
        self.config = self.load_config(config_file)
        self.setup_logging()
        self.existing_jobs = set()
        self.session = requests.Session()
        self.setup_session()
        self.setup_filters()
        self.current_year = datetime.now().year
        
        # CRITICAL: Check Ollama connection at startup - FAIL FAST if not available
        if not self.startup_ollama_check():
            self.logger.error("💥 STOPPING: Cannot proceed without Ollama")
            sys.exit(1)
        
        self.setup_google_sheets()
        warnings.filterwarnings("ignore")
        
    def startup_ollama_check(self) -> bool:
        """Check Ollama connection at startup - FAIL FAST if not available"""
        try:
            self.logger.info("🤖 Testing Ollama connection...")
            test_response = ollama.chat(
                model=self.config['ollama_model'],
                messages=[{'role': 'user', 'content': 'test'}]
            )
            self.logger.info(f"✅ Ollama ({self.config['ollama_model']}) connection successful")
            return True
        except Exception as e:
            self.logger.error("❌ OLLAMA CONNECTION FAILED!")
            self.logger.error(f"Error: {e}")
            self.logger.error("")
            self.logger.error("🚑 SOLUTION:")
            self.logger.error("  1. Start Ollama service: ollama serve")
            self.logger.error(f"  2. Pull model: ollama pull {self.config['ollama_model']}")
            self.logger.error(f"  3. Test: ollama run {self.config['ollama_model']}")
            self.logger.error("  4. Then run this program again")
            self.logger.error("")
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
        
    def get_or_create_worksheet(self, sheet_name: str, headers: List[str]):
        """Get or create a worksheet with specified headers"""
        try:
            spreadsheet = self.gc.open(self.sheet_name)
            
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
            except gspread.exceptions.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(sheet_name, 1000, 10)
                worksheet.append_row(headers)
                self.setup_sheet_formatting(worksheet)
                self.logger.info(f"✅ Created {sheet_name} with headers")
            
            return worksheet
        except Exception as e:
            self.logger.error(f"❌ Error accessing {sheet_name}: {e}")
            return None
    
    def setup_sheet_formatting(self, worksheet):
        """Set up Google Sheet formatting with proper column widths"""
        try:
            # Column width settings
            column_widths = [
                (0, 1, 300),   # Title
                (1, 2, 150),   # Company
                (2, 3, 100),   # Date Posted
                (3, 4, 400),   # Description
                (4, 5, 400),   # Qualifications
                (5, 6, 120),   # Location
                (6, 7, 200),   # URL
                (7, 8, 100)    # Date Added
            ]
            
            requests = []
            for start_idx, end_idx, width in column_widths:
                requests.append({
                    'updateDimensionProperties': {
                        'range': {
                            'sheetId': worksheet.id,
                            'dimension': 'COLUMNS',
                            'startIndex': start_idx,
                            'endIndex': end_idx
                        },
                        'properties': {'pixelSize': width},
                        'fields': 'pixelSize'
                    }
                })
            
            worksheet.spreadsheet.batch_update({'requests': requests})
            
            # Format header row
            worksheet.format('A1:H1', {
                'backgroundColor': {'red': 0.2, 'green': 0.6, 'blue': 0.9},
                'textFormat': {'bold': True, 'fontSize': 12, 'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}},
                'horizontalAlignment': 'CENTER',
                'verticalAlignment': 'MIDDLE'
            })
            
            # Freeze header row
            worksheet.spreadsheet.batch_update({
                'requests': [{
                    'updateSheetProperties': {
                        'properties': {
                            'sheetId': worksheet.id,
                            'gridProperties': {'frozenRowCount': 1}
                        },
                        'fields': 'gridProperties.frozenRowCount'
                    }
                }]
            })
            
        except Exception as e:
            self.logger.error(f"❌ Sheet formatting error: {e}")
    
    def load_existing_jobs_from_sheets(self):
        """Load existing jobs from all sheets (Sheet2, Sheet3, Sheet4)"""
        existing_jobs = set()
        
        for sheet_name in ["Sheet2", "Sheet3", "Sheet4"]:
            try:
                headers = ['Title', 'Company', 'Date Posted', 'Description', 'Qualifications', 'Location', 'URL', 'Date Added']
                worksheet = self.get_or_create_worksheet(sheet_name, headers)
                if not worksheet:
                    continue
                    
                all_values = worksheet.get_all_values()
                if len(all_values) <= 1:
                    continue
                
                for row in all_values[1:]:
                    if len(row) >= 7:
                        title, company, _, _, _, location, _ = row[:7]
                        if title and company:
                            job_id = self.create_job_id(title, company, location)
                            existing_jobs.add(job_id)
                            
            except Exception as e:
                self.logger.error(f"❌ Error loading jobs from {sheet_name}: {e}")
        
        self.logger.info(f"📊 Loaded {len(existing_jobs)} existing jobs from Google Sheets")
        return existing_jobs
    
    def setup_filters(self):
        """Setup clean, non-redundant filtering"""
        # Software engineering keywords (comprehensive)
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
        
        # Israeli cities - WHITELIST ONLY
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
        
        # Check keywords
        for keyword in self.sw_engineering_keywords:
            if keyword in title_lower:
                return True
        
        # Pattern matching for variations
        if re.search(r'software.*engineer|engineer.*software', title_lower):
            return True
        
        return False
    
    def is_israeli_location(self, location: str) -> bool:
        """STRICT whitelist-only approach"""
        if not self.config.get('filter_israel_locations_only', True):
            return True
            
        if not location or location.strip() == "":
            return False  # Reject empty locations
        
        location_clean = location.strip()
        location_lower = location_clean.lower()
        
        # ONLY accept if explicitly Israeli
        if 'israel' in location_lower or 'ישראל' in location_clean:
            return True
        
        # Or known Israeli city
        for city in self.israeli_cities:
            if city in location_lower:
                return True
        
        # Everything else: REJECT
        return False
    
    def parse_job_date(self, date_string: str) -> Tuple[bool, str]:
        """Parse job date and validate it's from current year"""
        if not date_string or date_string.strip() == "":
            return True, "**PDNA**"  # Post Date Not Available
        
        date_lower = date_string.lower().strip()
        
        # Try to extract year
        year_match = re.search(r'20(\\d{2})', date_string)
        if year_match:
            year = int(f"20{year_match.group(1)}")
            if self.config.get('filter_by_current_year', True):
                if year < self.current_year:
                    return False, ""  # Old job, reject
            return True, date_string
        
        # If no year found, accept with PDNA indicator
        return True, "**PDNA**"
    
    # NEW SHEET ORGANIZATION - V4.1
    def is_senior_position(self, title: str) -> bool:
        """Check if position is senior level (Sheet4)"""
        title_lower = title.lower()
        return 'senior' in title_lower
    
    def is_student_intern_position(self, title: str) -> bool:
        """Check if position is for students/interns (Sheet2) - FIXED REGEX"""
        title_lower = title.lower()
        
        # FIXED: Use word boundaries to avoid "internet" false positive
        if re.search(r'\\bintern\\b', title_lower):      # "intern" as complete word
            return True
        if re.search(r'\\binternship\\b', title_lower):  # "internship" as complete word
            return True
        if re.search(r'\\bstudent\\b', title_lower):     # "student" as complete word
            return True
        if re.search(r'\\btrainee\\b', title_lower):     # "trainee" as complete word
            return True
        if re.search(r'\\bapprentice\\b', title_lower):  # "apprentice" as complete word
            return True
        
        return False
    
    def is_entry_junior_position(self, title: str) -> bool:
        """Check if position is entry/junior level (Sheet3)"""
        if self.is_student_intern_position(title):
            return False  # These go to Sheet2, not Sheet3
        if self.is_senior_position(title):
            return False  # These go to Sheet4, not Sheet3
            
        title_lower = title.lower()
        entry_keywords = ['entry', 'junior', 'graduate', 'new grad', 'fresh', 'associate']
        return any(keyword in title_lower for keyword in entry_keywords)
    
    def categorize_job(self, title: str) -> str:
        """Categorize job into appropriate sheet - NEW V4.1 LOGIC"""
        if self.is_senior_position(title):
            return "Sheet4"  # Senior positions
        elif self.is_student_intern_position(title):
            return "Sheet2"  # Student/Intern positions (SWAPPED)
        elif self.is_entry_junior_position(title):
            return "Sheet3"  # Entry/Graduate positions (SWAPPED)
        else:
            return "Sheet3"  # Default: Regular jobs go with entry jobs
    
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
        """Scrape with requests - Only returns on success or final failure"""
        for attempt in range(self.config['max_retries']):
            try:
                response = self.session.get(url, timeout=self.config['timeout'])
                response.encoding = 'utf-8'
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.decompose()
                
                text = soup.get_text(separator=' ', strip=True)
                text = re.sub(r'\\s+', ' ', text)
                
                return text, soup  # SUCCESS - return immediately
                
            except requests.RequestException:
                if attempt < self.config['max_retries'] - 1:
                    time.sleep(2 ** attempt)
                    continue
        
        return None, None  # All attempts failed
    
    def scrape_with_selenium(self, url):
        """Scrape with Selenium - ONLY called if requests fails"""
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
        """ROBUST JSON extraction from LLM response"""
        try:
            # Remove markdown code blocks
            response_text = re.sub(r'```json\\s*', '', response_text)
            response_text = re.sub(r'```\\s*', '', response_text)
            
            # Find JSON boundaries
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start == -1 or json_end <= json_start:
                return None
            
            json_str = response_text[json_start:json_end]
            
            # Fix common JSON issues
            json_str = re.sub(r',\\s*([}\\]])', r'\\1', json_str)  # Remove trailing commas
            json_str = re.sub(r'\\n', ' ', json_str)  # Remove newlines
            
            return json.loads(json_str)
            
        except json.JSONDecodeError:
            return None
    
    def enhanced_ollama_analysis(self, content, company_url):
        """Improved Ollama analysis with robust JSON extraction"""
        company_name = self.extract_company_name_from_url(company_url)
        
        prompt = f"""Extract software engineering jobs from {company_name}.

Rules:
1. ONLY software engineering roles
2. Return VALID JSON only
3. Include date posted if available

Content:
{content[:8000]}

Return ONLY this JSON (no markdown, no extra text):
{{
  "jobs": [
    {{
      "title": "Software Engineer",
      "location": "Tel Aviv",
      "description": "Brief summary",
      "qualifications": "Key requirements",
      "date_posted": "2025-10-14 or empty",
      "url": "{company_url}"
    }}
  ]
}}
"""
        
        try:
            self.logger.debug(f"🤖 Analyzing {company_name} with Ollama...")
            response = ollama.chat(
                model=self.config['ollama_model'],
                messages=[{'role': 'user', 'content': prompt}]
            )
            
            job_data = self.extract_json_from_llm_response(response['message']['content'])
            if not job_data:
                self.logger.debug(f"⚠️ No valid JSON from {company_name}")
                return []
            
            jobs = job_data.get('jobs', [])
            self.logger.debug(f"📊 Extracted {len(jobs)} potential jobs from {company_name}")
            
            # Apply all filters
            filtered_jobs = []
            for job in jobs:
                # Must have title
                if not job.get('title'):
                    continue
                
                # Software engineering role check
                if not self.is_software_engineering_role(job.get('title', '')):
                    self.logger.debug(f"⚠️ Non-SW role filtered: {job.get('title', '')}")
                    continue
                
                # Location check (STRICT)
                if not self.is_israeli_location(job.get('location', '')):
                    self.logger.debug(f"⚠️ Non-Israeli location: {job.get('location', '')}")
                    continue
                
                # Date validation
                date_valid, formatted_date = self.parse_job_date(job.get('date_posted', ''))
                if not date_valid:
                    self.logger.debug(f"⚠️ Old job filtered: {job.get('date_posted', '')}")
                    continue  # Skip old jobs
                
                job['date_posted'] = formatted_date
                job['company'] = company_name
                job.setdefault('description', 'Description not available')
                job.setdefault('qualifications', 'Qualifications not specified')
                job.setdefault('url', company_url)
                
                filtered_jobs.append(job)
            
            if filtered_jobs:
                self.logger.debug(f"✅ {len(filtered_jobs)} jobs passed all filters from {company_name}")
            
            return filtered_jobs
            
        except Exception as e:
            self.logger.error(f"❌ Ollama analysis failed for {company_name}: {e}")
            return []
    
    def scrape_company_jobs(self, url):
        """Scrape jobs - Selenium only runs if requests fails"""
        self.logger.info(f"🔍 {urlparse(url).netloc}")
        
        # Try requests first
        scraped_content, soup = self.scrape_with_requests(url)
        
        # ONLY try Selenium if requests failed
        if not scraped_content and self.config['use_selenium_for_js']:
            self.logger.info(f"  ↳ Requests failed, trying Selenium...")
            scraped_content, soup = self.scrape_with_selenium(url)
        
        if not scraped_content:
            self.logger.warning(f"⚠️ Failed to scrape {urlparse(url).netloc}")
            return []
        
        # Analyze content with Ollama
        jobs = self.enhanced_ollama_analysis(scraped_content, url)
        
        # Filter duplicates
        new_jobs = []
        for job in jobs:
            job_id = self.create_job_id(job['title'], job['company'], job.get('location', ''))
            if job_id not in self.existing_jobs:
                job['date_added'] = datetime.now().strftime('%Y-%m-%d')
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
    
    def write_batch_with_retry(self, worksheet, batch_rows, sheet_type):
        """Write batch with retry and formatting"""
        for attempt in range(3):
            try:
                if not batch_rows:
                    return True
                
                worksheet.append_rows(batch_rows)
                
                total_rows = len(worksheet.get_all_values())
                start_row = total_rows - len(batch_rows) + 1
                
                # Format rows
                for i, row_data in enumerate(batch_rows):
                    row_number = start_row + i
                    title = row_data[0]
                    
                    try:
                        # Bold for entry/junior in Sheet3 (not Sheet2 for interns)
                        if sheet_type == "Sheet3" and self.is_entry_junior_position(title):
                            worksheet.format(f'A{row_number}', {
                                'textFormat': {'bold': True},
                                'wrapStrategy': 'WRAP'
                            })
                        
                        # Wrap description/qualifications
                        worksheet.format(f'D{row_number}:E{row_number}', {
                            'wrapStrategy': 'WRAP',
                            'verticalAlignment': 'TOP'
                        })
                        
                        # Row height
                        worksheet.spreadsheet.batch_update({
                            'requests': [{
                                'updateDimensionProperties': {
                                    'range': {
                                        'sheetId': worksheet.id,
                                        'dimension': 'ROWS',
                                        'startIndex': row_number - 1,
                                        'endIndex': row_number
                                    },
                                    'properties': {'pixelSize': 80},
                                    'fields': 'pixelSize'
                                }
                            }]
                        })
                    except:
                        pass
                
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
        """Save jobs to appropriate sheets with NEW V4.1 categorization"""
        if not all_jobs or not self.gc:
            return
        
        # NEW: Categorize jobs into 3 sheets
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
        
        headers = ['Title', 'Company', 'Date Posted', 'Description', 'Qualifications', 'Location', 'URL', 'Date Added']
        
        # Save to appropriate sheets
        if sheet2_jobs:
            self.save_to_sheet("Sheet2", sheet2_jobs, headers, "Student/Intern")
        
        if sheet3_jobs:
            self.save_to_sheet("Sheet3", sheet3_jobs, headers, "Entry/Regular")
        
        if sheet4_jobs:
            self.save_to_sheet("Sheet4", sheet4_jobs, headers, "Senior")
    
    def save_to_sheet(self, sheet_name, jobs, headers, category):
        """Save jobs to specific sheet"""
        try:
            worksheet = self.get_or_create_worksheet(sheet_name, headers)
            if not worksheet:
                return
            
            batch_size = self.config.get('sheets_batch_size', 10)
            delay = self.config.get('sheets_write_delay', 6)
            
            self.logger.info(f"💾 Saving {len(jobs)} {category} jobs to {sheet_name}")
            
            # Prepare rows
            all_rows = []
            for job in jobs:
                row = [
                    job.get('title', ''),
                    job.get('company', ''),
                    job.get('date_posted', ''),
                    job.get('description', ''),
                    job.get('qualifications', ''),
                    job.get('location', ''),
                    job.get('url', ''),
                    job.get('date_added', '')
                ]
                all_rows.append(row)
            
            # Write in batches
            total_batches = (len(all_rows) + batch_size - 1) // batch_size
            successful = 0
            
            for i in range(0, len(all_rows), batch_size):
                batch = all_rows[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                
                self.logger.info(f"  📤 Batch {batch_num}/{total_batches}")
                
                if self.write_batch_with_retry(worksheet, batch, sheet_name):
                    successful += len(batch)
                
                if i + batch_size < len(all_rows):
                    time.sleep(delay)
            
            self.logger.info(f"✅ Saved {successful}/{len(jobs)} to {sheet_name}")
            
        except Exception as e:
            self.logger.error(f"❌ Error saving to {sheet_name}: {e}")
    
    def run(self):
        """Main execution with fail-fast Ollama check"""
        start_time = datetime.now()
        self.logger.info("🚀 Job Scraper V4.1 - Enhanced with Fail-Fast Ollama Check")
        
        if not self.gc:
            self.logger.error("❌ Google Sheets not configured")
            return
        
        self.existing_jobs = self.load_existing_jobs_from_sheets()
        
        urls = self.load_company_urls()
        if not urls:
            self.logger.error("❌ No URLs")
            return
        
        self.logger.info(f"📊 NEW SHEET ORGANIZATION:")
        self.logger.info(f"  • Sheet2: Student/Intern positions")
        self.logger.info(f"  • Sheet3: Entry/Junior + Regular positions (bold entry)")
        self.logger.info(f"  • Sheet4: Senior positions")
        
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
        self.logger.info(f"🎉 COMPLETED in {duration}")
        self.logger.info(f"💼 Total jobs: {len(all_jobs)}")
        self.logger.info("=" * 60)

def main():
    try:
        scraper = JobScraperV41()
        scraper.run()
    except KeyboardInterrupt:
        logging.info("⚠️ Interrupted")
    except SystemExit:
        pass  # Allow sys.exit() from Ollama check
    except Exception as e:
        logging.error(f"💥 Error: {e}")

if __name__ == "__main__":
    main()
'''

with open('job_scraper_v4_1_fail_fast.py', 'w', encoding='utf-8') as f:
    f.write(v4_1_complete)

print("✅ Created job_scraper_v4_1_fail_fast.py")
print()
print("🎯 V4.1 COMPLETE FIXES:")
print("=" * 30)
print("1. 🚨 FAIL FAST: Stops immediately if Ollama not running")
print("2. 📊 NEW SHEETS:")
print("   • Sheet2: Student/Intern positions")
print("   • Sheet3: Entry/Junior + Regular (bold entry)")  
print("   • Sheet4: Senior positions")
print("3. 🐛 REGEX FIX: 'Internet' no longer triggers intern detection")
print("4. 🔍 DEBUG LOGGING: Shows filtering decisions")
print("5. ✅ PROPER ERROR HANDLING: Clear Ollama connection messages")
print()
print("Now Ollama failures will be caught immediately at startup!")
print("No more 16-minute runs that result in 0 jobs!")