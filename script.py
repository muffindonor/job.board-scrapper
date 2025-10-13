# Create the rate-limited batch writing version (V3.1)
rate_limited_scraper = '''
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
from typing import List, Dict, Optional, Set

class RateLimitedJobScraper:
    def __init__(self, config_file='config.json'):
        """Rate-limited job scraper with batch Google Sheets writing"""
        self.config = self.load_config(config_file)
        self.setup_logging()
        self.existing_jobs = set()  # Will load from Google Sheets
        self.session = requests.Session()
        self.setup_session()
        self.setup_filters()
        self.setup_google_sheets()
        
        # Rate limiting settings for Google Sheets API
        self.batch_size = 10  # Write jobs in batches of 10
        self.write_delay = 6   # 6 seconds between batches (10 requests per minute = safe)
        self.max_retries = 3   # Retry failed writes
        
        warnings.filterwarnings("ignore")
        
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
        
    def get_worksheet(self):
        """Get or create Google Sheet worksheet (Sheet2)"""
        try:
            spreadsheet = self.gc.open(self.sheet_name)
            
            # Try to get Sheet2, create if doesn't exist
            try:
                worksheet = spreadsheet.worksheet("Sheet2")
            except gspread.exceptions.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet("Sheet2", 1000, 10)
                # Set up headers
                headers = ['Title', 'Company', 'Date Posted', 'Date Added', 
                          'Description', 'Qualifications', 'Location', 'URL']
                worksheet.append_row(headers)
                self.setup_sheet_formatting(worksheet)
                self.logger.info("✅ Created Sheet2 with headers")
            
            return worksheet
        except Exception as e:
            self.logger.error(f"❌ Error accessing Google Sheet: {e}")
            return None
    
    def setup_sheet_formatting(self, worksheet):
        """Set up Google Sheet formatting with proper column widths"""
        try:
            # Column width settings (pixels)
            column_widths = [
                (0, 1, 300),   # Title - Wide
                (1, 2, 150),   # Company - Medium
                (2, 3, 100),   # Date Posted - Narrow
                (3, 4, 100),   # Date Added - Narrow  
                (4, 5, 400),   # Description - Very Wide
                (5, 6, 400),   # Qualifications - Very Wide
                (6, 7, 120),   # Location - Medium
                (7, 8, 150)    # URL - Narrow
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
            
            # Apply column width changes
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
    
    def load_existing_jobs_from_sheet(self):
        """Load existing jobs from Google Sheets to avoid duplicates"""
        try:
            worksheet = self.get_worksheet()
            if not worksheet:
                return set()
                
            all_values = worksheet.get_all_values()
            if len(all_values) <= 1:  # Only headers or empty
                return set()
            
            existing_jobs = set()
            for row in all_values[1:]:  # Skip header
                if len(row) >= 8:  # Ensure we have all columns
                    title, company, _, _, _, _, location, _ = row[:8]
                    if title and company:
                        job_id = self.create_job_id(title, company, location)
                        existing_jobs.add(job_id)
            
            self.logger.info(f"📊 Loaded {len(existing_jobs)} existing jobs from Google Sheets")
            return existing_jobs
            
        except Exception as e:
            self.logger.error(f"❌ Error loading existing jobs from sheet: {e}")
            return set()
    
    def setup_filters(self):
        """Setup comprehensive filtering with relaxed location rules"""
        # Expanded software engineering keywords (very inclusive)
        self.sw_engineering_keywords = {
            # Core terms that should ALWAYS be included
            "software engineer", "software developer", "developer", "engineer", "programmer",
            "full stack", "frontend", "front-end", "backend", "back-end", "web developer",
            "mobile developer", "ios developer", "android developer", "react developer",
            "angular developer", "vue developer", "node.js developer", "python developer",
            "java developer", ".net developer", "c# developer", "php developer", "ruby developer",
            "javascript developer", "typescript developer", "go developer", "kotlin developer",
            "swift developer", "flutter developer", "react native developer",
            "junior software", "senior software", "staff software", "principal software",
            "lead software", "technical lead", "tech lead", "engineering lead", "team lead",
            "software architect", "solution architect", "system architect", "technical architect",
            "cloud architect", "api developer", "systems engineer", "platform engineer",
            "infrastructure engineer", "site reliability", "sre", "devops engineer",
            "devsecops engineer", "build engineer", "release engineer", "automation engineer",
            "ci/cd engineer", "cloud engineer", "aws engineer", "azure engineer", "gcp engineer",
            "kubernetes engineer", "docker engineer", "qa engineer", "test engineer",
            "automation test", "sdet", "performance engineer", "security engineer",
            "data engineer", "ml engineer", "machine learning engineer", "ai engineer",
            "mlops engineer", "embedded software", "firmware engineer", "game developer",
            "blockchain developer", "web3 developer", "ar/vr developer", "computer vision"
        }
        
        # Israeli cities (comprehensive) - BUT we'll be more lenient about location filtering
        self.israeli_cities = {
            "jerusalem", "tel aviv", "tel aviv-yafo", "haifa", "petah tikva", "rishon lezion",
            "netanya", "ashdod", "bnei brak", "beersheba", "beer sheva", "holon", "ramat gan",
            "beit shemesh", "ashkelon", "rehovot", "bat yam", "herzliya", "hadera", "kfar saba",
            "modi'in", "lod", "givat shmuel", "raanana", "givatayim", "hod hasharon",
            "or yehuda", "yehud", "kiryat ata", "kiryat bialik", "kiryat motzkin", "kiryat yam",
            "kiryat ono", "kiryat gat", "kiryat malachi", "kiryat shmona", "nazareth", "nahariya",
            "acre", "akko", "tiberias", "eilat", "dimona", "arad", "carmiel", "ma'ale adumim",
            "modiin", "rosh haayin", "bet shean", "afula", "migdal haemek", "yokneam", "nesher",
            "or akiva", "pardes hanna-karkur", "caesarea", "zichron yaakov", "binyamina",
            "kiryat tivon", "karmiel", "safed", "tzfat", "maalot-tarshiha", "shlomi", "tamra",
            "shfaram", "tirat carmel", "yerushalayim", "hefa", "rishon leziyyon", "herzliyya",
            "be'er sheva", "petah tiqwa", "central district", "tel aviv district", "haifa district",
            "northern district", "southern district", "jerusalem district", "israel"
        }
        
        # Keep list of definitely excluded countries (but be more lenient)
        self.definitely_excluded_countries = {
            "united states", "usa", "canada", "united kingdom", "uk", "germany", "france",
            "china", "india", "singapore", "australia", "japan", "south korea"
        }
    
    def load_config(self, config_file):
        """Load enhanced configuration"""
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
            # New rate limiting settings
            "sheets_batch_size": 10,
            "sheets_write_delay": 6
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
        """Setup requests session with Hebrew support"""
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,he;q=0.8',
            'Accept-Charset': 'utf-8'
        })
    
    def setup_logging(self):
        """Setup clean logging"""
        logs_dir = Path('logs')
        logs_dir.mkdir(exist_ok=True)
        
        log_file = logs_dir / f'job_scraper_{datetime.now().strftime("%Y%m%d")}.log'
        
        # Minimal logging format
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        
        logging.basicConfig(
            level=getattr(logging, self.config['log_level']),
            format=log_format,
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Suppress noisy loggers
        for noisy_logger in ['urllib3', 'selenium', 'webdriver_manager', 'requests', 'gspread']:
            logging.getLogger(noisy_logger).setLevel(logging.ERROR)
    
    def create_job_id(self, title, company, location):
        """Create unique job ID"""
        job_string = f"{title}_{company}_{location}".lower().strip()
        job_string = re.sub(r'[^a-zA-Z0-9_]', '', job_string)
        return hashlib.md5(job_string.encode('utf-8')).hexdigest()
    
    def is_software_engineering_role(self, job_title: str) -> bool:
        """Enhanced software role detection - much more inclusive"""
        if not self.config.get('filter_software_roles_only', True):
            return True
            
        title_lower = job_title.lower().strip()
        
        # Check against comprehensive keywords
        for keyword in self.sw_engineering_keywords:
            if keyword in title_lower:
                return True
        
        # Special patterns for variations like "Software Engineer, [Specialty]"
        if re.search(r'software.*engineer|engineer.*software', title_lower):
            return True
        if re.search(r'developer|programmer|engineer', title_lower) and 'software' in title_lower:
            return True
        
        return False
    
    def is_israeli_location(self, location: str) -> bool:
        """Much more lenient location filtering"""
        if not self.config.get('filter_israel_locations_only', True):
            return True
            
        if not location or location.strip() == "":
            return True  # Allow empty locations
        
        location_clean = location.strip()
        location_lower = location_clean.lower()
        
        # If explicitly mentions Israel, accept it
        if 'israel' in location_lower or 'ישראל' in location_clean:
            return True
        
        # Check for Israeli cities
        for city in self.israeli_cities:
            if city in location_lower:
                return True
        
        # Check for definitely excluded countries - only reject if explicitly mentioned
        for country in self.definitely_excluded_countries:
            if country in location_lower and 'israel' not in location_lower:
                return False
        
        # If it's just a city name or unclear, assume it could be Israeli
        return True
    
    def create_silent_chrome_driver(self):
        """Create Chrome driver with ALL noise suppressed including WebGL"""
        chrome_options = Options()
        
        if self.config['headless_browser']:
            chrome_options.add_argument("--headless=new")
        
        # Comprehensive noise suppression
        suppression_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage", 
            "--disable-gpu",
            "--disable-web-security",
            "--disable-features=VizDisplayCompositor",
            "--disable-features=TranslateUI,BlinkGenPropertyTrees",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-logging",
            "--disable-extensions",
            "--disable-plugins",
            "--disable-sync", 
            "--disable-translate",
            "--disable-dev-tools",
            "--disable-background-networking",
            "--log-level=3",  # Only fatal errors
            "--silent",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-default-apps",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-hang-monitor",
            "--disable-client-side-phishing-detection",
            "--disable-component-update",
            "--disable-domain-reliability",
            "--disable-features=AudioServiceOutOfProcess",
            "--disable-features=MediaRouter",
            "--disable-ipc-flooding-protection",
            "--window-size=1920,1080",
            # WebGL specific suppression
            "--disable-webgl",
            "--disable-webgl2", 
            "--disable-3d-apis",
            "--disable-webgl-image-chromium",
            "--disable-webgl-extensions"
        ]
        
        for arg in suppression_args:
            chrome_options.add_argument(arg)
        
        chrome_options.add_experimental_option("excludeSwitches", 
                                             ["enable-automation", "enable-logging"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Disable images and other resources for speed
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_settings.popups": 0,
            "profile.managed_default_content_settings.media_stream": 2,
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        try:
            service = Service(ChromeDriverManager().install())
            service.log_path = os.devnull if hasattr(os, 'devnull') else 'NUL'
            
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            self.logger.error(f"❌ Chrome driver creation failed: {e}")
            return None
    
    def load_company_urls(self):
        """Load URLs with better error handling"""
        urls = []
        urls_file = self.config['urls_file']
        
        if not os.path.exists(urls_file):
            sample_urls = [
                "# Israeli Company Career Pages - Add your targets here",
                "# Lines starting with # are ignored",
                "",
                "# Examples (replace with actual Israeli companies):",
                "https://careers.microsoft.com/professionals/us/en/search-results",
                "https://careers.google.com/jobs/results/",
                "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
                "# Add more Israeli tech company URLs here"
            ]
            with open(urls_file, 'w', encoding='utf-8') as f:
                f.write('\\n'.join(sample_urls))
            self.logger.info(f"📝 Created sample URLs file: {urls_file}")
            
        with open(urls_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    urls.append(line)
                    
        self.logger.info(f"📋 Loaded {len(urls)} URLs to scrape")
        return urls
    
    def extract_job_links(self, soup, base_url):
        """Extract job posting links with better patterns"""
        job_links = []
        
        # Enhanced job link patterns
        job_link_patterns = [
            'a[href*="job"]', 'a[href*="position"]', 'a[href*="career"]',
            'a[href*="/jobs/"]', 'a[href*="/careers/"]', 'a[href*="/positions/"]',
            'a[href*="requisition"]', 'a[href*="opening"]', 'a[href*="opportunity"]',
            '.job-link', '.position-link', '.career-link', '.job-tile',
            '[data-job-id]', '[data-position-id]', '[data-requisition]'
        ]
        
        for pattern in job_link_patterns:
            links = soup.select(pattern)
            for link in links:
                href = link.get('href')
                if href:
                    full_url = urljoin(base_url, href)
                    if (full_url not in job_links and 
                        not any(skip in href.lower() for skip in ['page=', 'next', 'prev', 'filter'])):
                        job_links.append(full_url)
        
        max_crawl = self.config.get('max_crawl_depth', 5)
        return job_links[:max_crawl]
    
    def scrape_individual_job(self, job_url):
        """Scrape individual job with better content extraction"""
        try:
            response = self.session.get(job_url, timeout=self.config['timeout'])
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove noise
            for element in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
                element.decompose()
            
            text = soup.get_text(separator=' ', strip=True)
            text = re.sub(r'\\s+', ' ', text)
            
            return text[:self.config.get('content_length_limit', 10000)]
            
        except Exception:
            return None
    
    def scrape_with_requests(self, url):
        """Enhanced requests scraping"""
        for attempt in range(self.config['max_retries']):
            try:
                response = self.session.get(url, timeout=self.config['timeout'])
                response.encoding = 'utf-8'
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Remove noise
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
        """Enhanced Selenium scraping with noise suppression"""
        driver = self.create_silent_chrome_driver()
        if not driver:
            return None, None
            
        try:
            driver.get(url)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Wait and scroll for dynamic content
            time.sleep(3)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Remove noise
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
    
    def enhanced_ollama_analysis(self, content, company_url, job_links=None):
        """Improved Ollama analysis with better JSON handling"""
        company_name = self.extract_company_name_from_url(company_url)
        
        # Much more focused prompt with better JSON structure
        prompt = f"""
        Extract software engineering jobs from {company_name} career page content.

        CRITICAL RULES:
        1. ONLY software engineering roles (any title with: software, developer, engineer, programmer, devops, qa, data engineer, etc.)
        2. Include ALL variations like "Software Engineer, [Specialization]" 
        3. For locations: prefer Israeli locations but don't be too strict
        4. Return VALID JSON ONLY

        Content:
        {content[:self.config.get('content_length_limit', 8000)]}

        Return this JSON structure ONLY:
        {{
          "jobs": [
            {{
              "title": "Software Engineer",
              "location": "Tel Aviv",
              "description": "Brief role summary",
              "qualifications": "Key requirements",
              "date_posted": "2023-10-13 or empty",
              "url": "{company_url}"
            }}
          ]
        }}
        
        Maximum {self.config.get('max_jobs_per_site', 30)} jobs. Valid JSON only.
        """
        
        try:
            response = ollama.chat(
                model=self.config['ollama_model'],
                messages=[{'role': 'user', 'content': prompt}]
            )
            
            response_text = response['message']['content'].strip()
            
            # Better JSON extraction
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                
                # Try to fix common JSON issues
                json_str = re.sub(r',\\s*}', '}', json_str)  # Remove trailing commas
                json_str = re.sub(r',\\s*]', ']', json_str)  # Remove trailing commas in arrays
                
                try:
                    job_data = json.loads(json_str)
                    jobs = job_data.get('jobs', [])
                    
                    # Apply filtering and add metadata
                    filtered_jobs = []
                    for job in jobs:
                        if (job.get('title') and 
                            self.is_software_engineering_role(job.get('title', '')) and 
                            self.is_israeli_location(job.get('location', ''))):
                            
                            job['company'] = company_name
                            job.setdefault('date_posted', '')
                            job.setdefault('description', 'Description not available')
                            job.setdefault('qualifications', 'Qualifications not specified')
                            if not job.get('url') or job['url'] == company_url:
                                job['url'] = company_url
                            filtered_jobs.append(job)
                    
                    return filtered_jobs
                    
                except json.JSONDecodeError as e:
                    self.logger.debug(f"JSON parse error for {company_url}: {e}")
                    
        except Exception as e:
            self.logger.debug(f"Ollama analysis error for {company_url}: {e}")
            
        return []
    
    def scrape_company_jobs(self, url):
        """Enhanced job scraping with better error handling"""
        self.logger.info(f"🔍 Processing: {urlparse(url).netloc}")
        
        # Scrape main career page
        scraped_content, soup = self.scrape_with_requests(url)
        
        if not scraped_content and self.config['use_selenium_for_js']:
            scraped_content, soup = self.scrape_with_selenium(url)
        
        if not scraped_content:
            self.logger.warning(f"⚠️ No content scraped from {urlparse(url).netloc}")
            return []
        
        all_jobs = []
        
        # Analyze main page
        main_jobs = self.enhanced_ollama_analysis(scraped_content, url)
        all_jobs.extend(main_jobs)
        
        # Crawl individual job pages if enabled and we found jobs
        if (self.config.get('enable_job_crawling', True) and soup and len(main_jobs) > 0):
            job_links = self.extract_job_links(soup, url)
            
            if job_links:
                for i, job_url in enumerate(job_links):
                    if i >= self.config.get('max_crawl_depth', 5):
                        break
                        
                    job_content = self.scrape_individual_job(job_url)
                    if job_content:
                        individual_jobs = self.enhanced_ollama_analysis(job_content, job_url)
                        for job in individual_jobs:
                            job['url'] = job_url
                        all_jobs.extend(individual_jobs)
                    
                    time.sleep(1)
        
        # Filter duplicates and add metadata
        new_jobs = []
        for job in all_jobs:
            if not all([job.get('title'), job.get('company')]):
                continue
                
            job_id = self.create_job_id(job['title'], job['company'], job.get('location', ''))
            if job_id not in self.existing_jobs:
                job['date_added'] = datetime.now().strftime('%Y-%m-%d')
                new_jobs.append(job)
                self.existing_jobs.add(job_id)
        
        if new_jobs:
            self.logger.info(f"✅ Found {len(new_jobs)} new software engineering jobs")
        
        return new_jobs
    
    def extract_company_name_from_url(self, url):
        """Enhanced company name extraction"""
        try:
            domain = urlparse(url).netloc.lower()
            domain = domain.replace('www.', '').replace('careers.', '').replace('jobs.', '')
            company = domain.split('.')[0]
            
            company_mapping = {
                'amazon': 'Amazon', 'google': 'Google', 'microsoft': 'Microsoft',
                'apple': 'Apple', 'netflix': 'Netflix', 'meta': 'Meta',
                'facebook': 'Meta', 'linkedin': 'LinkedIn', 'salesforce': 'Salesforce',
                'nvidia': 'NVIDIA', 'intel': 'Intel', 'amd': 'AMD', 'oracle': 'Oracle'
            }
            
            return company_mapping.get(company, company.title())
        except:
            return "Unknown Company"
    
    def is_entry_level_job(self, title):
        """Check if job is entry/student/intern position"""
        entry_keywords = [
            'intern', 'internship', 'student', 'entry', 'junior', 'graduate', 
            'new grad', 'fresh', 'trainee', 'apprentice', 'associate'
        ]
        title_lower = title.lower()
        return any(keyword in title_lower for keyword in entry_keywords)
    
    def write_batch_to_sheets_with_retry(self, worksheet, batch_rows):
        """Write a batch of rows to Google Sheets with retry logic"""
        for attempt in range(self.max_retries):
            try:
                # Prepare batch data for append
                if batch_rows:
                    worksheet.append_rows(batch_rows)
                    
                    # Get starting row number for formatting
                    total_rows = len(worksheet.get_all_values())
                    start_row = total_rows - len(batch_rows) + 1
                    
                    # Format the batch
                    for i, row_data in enumerate(batch_rows):
                        row_number = start_row + i
                        title = row_data[0]
                        
                        try:
                            # Check if it's entry level for bold formatting
                            if self.is_entry_level_job(title):
                                # Bold title for entry/intern positions
                                worksheet.format(f'A{row_number}:A{row_number}', {
                                    'textFormat': {'bold': True, 'fontSize': 10},
                                    'wrapStrategy': 'WRAP',
                                    'verticalAlignment': 'TOP'
                                })
                            
                            # Format other columns with wrapping
                            worksheet.format(f'E{row_number}:F{row_number}', {  # Description, Qualifications
                                'wrapStrategy': 'WRAP',
                                'verticalAlignment': 'TOP',
                                'textFormat': {'fontSize': 10}
                            })
                            
                            # Set row height
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
                            
                        except Exception as e:
                            self.logger.debug(f"Formatting error for row {row_number}: {e}")
                    
                    return True  # Success
                    
            except APIError as e:
                if "429" in str(e):  # Quota exceeded
                    self.logger.warning(f"⚠️ Rate limit hit (attempt {attempt + 1}), waiting {self.write_delay * 2} seconds...")
                    time.sleep(self.write_delay * 2)  # Wait longer on rate limit
                    continue
                else:
                    self.logger.error(f"❌ API Error: {e}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.write_delay)
                        continue
                    else:
                        return False
            except Exception as e:
                self.logger.error(f"❌ Error writing batch: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.write_delay)
                    continue
                else:
                    return False
        
        return False
    
    def save_jobs_to_sheet(self, all_jobs):
        """Save jobs to Google Sheets with rate limiting and batch processing"""
        if not all_jobs:
            self.logger.info("📄 No new jobs to save")
            return
        
        if not self.gc:
            self.logger.error("❌ Google Sheets not configured")
            return
        
        try:
            worksheet = self.get_worksheet()
            if not worksheet:
                return
            
            self.logger.info(f"💾 Saving {len(all_jobs)} jobs in batches of {self.batch_size}")
            
            # Prepare all row data
            all_rows = []
            for job in all_jobs:
                title = job.get('title', '')
                company = job.get('company', '')
                date_posted = job.get('date_posted', '')
                date_added = job.get('date_added', '')
                description = job.get('description', '')
                qualifications = job.get('qualifications', '')
                location = job.get('location', '')
                url = job.get('url', '')
                
                row_data = [title, company, date_posted, date_added, description, qualifications, location, url]
                all_rows.append(row_data)
            
            # Process in batches with rate limiting
            total_batches = (len(all_rows) + self.batch_size - 1) // self.batch_size
            successful_jobs = 0
            
            for i in range(0, len(all_rows), self.batch_size):
                batch = all_rows[i:i + self.batch_size]
                batch_num = (i // self.batch_size) + 1
                
                self.logger.info(f"📤 Writing batch {batch_num}/{total_batches} ({len(batch)} jobs)...")
                
                success = self.write_batch_to_sheets_with_retry(worksheet, batch)
                
                if success:
                    successful_jobs += len(batch)
                    self.logger.info(f"✅ Batch {batch_num} saved successfully")
                else:
                    self.logger.error(f"❌ Failed to save batch {batch_num}")
                
                # Rate limiting delay between batches (except for last batch)
                if i + self.batch_size < len(all_rows):
                    self.logger.info(f"⏳ Waiting {self.write_delay} seconds (rate limiting)...")
                    time.sleep(self.write_delay)
            
            self.logger.info(f"🎉 Successfully saved {successful_jobs}/{len(all_jobs)} jobs to Google Sheets")
            
            if successful_jobs < len(all_jobs):
                self.logger.warning(f"⚠️ {len(all_jobs) - successful_jobs} jobs failed to save due to API limits")
            
            # Get sheet URL
            try:
                sheet_url = worksheet.spreadsheet.url
                self.logger.info(f"🔗 View results: {sheet_url}")
            except:
                pass
                
        except Exception as e:
            self.logger.error(f"❌ Error saving to Google Sheets: {e}")
    
    def run(self):
        """Main execution with comprehensive error handling"""
        start_time = datetime.now()
        self.logger.info("🚀 Rate-Limited Job Scraper V3.1 - Software Engineering Jobs for Israel")
        
        if not self.gc:
            self.logger.error("❌ Google Sheets not configured. Cannot proceed.")
            return
        
        # Load existing jobs from Google Sheets
        self.existing_jobs = self.load_existing_jobs_from_sheet()
        
        # Load URLs
        company_urls = self.load_company_urls()
        if not company_urls:
            self.logger.error("❌ No URLs found. Please add URLs to company_urls.txt")
            return
        
        all_new_jobs = []
        stats = {'successful': 0, 'failed': 0, 'total_jobs': 0}
        
        for i, url in enumerate(company_urls, 1):
            try:
                self.logger.info(f"[{i}/{len(company_urls)}] {urlparse(url).netloc}")
                jobs = self.scrape_company_jobs(url)
                all_new_jobs.extend(jobs)
                stats['total_jobs'] += len(jobs)
                
                if jobs:
                    stats['successful'] += 1
                else:
                    stats['failed'] += 1
                
                if i < len(company_urls):
                    time.sleep(self.config['delay_between_requests'])
                
            except Exception as e:
                self.logger.error(f"❌ Error processing {urlparse(url).netloc}: {e}")
                stats['failed'] += 1
                continue
        
        # Save to Google Sheets with rate limiting
        self.save_jobs_to_sheet(all_new_jobs)
        
        # Final summary
        duration = datetime.now() - start_time
        self.logger.info("=" * 60)
        self.logger.info("🎉 RATE-LIMITED JOB SCRAPING COMPLETED")
        self.logger.info("=" * 60)
        self.logger.info(f"⏱️  Duration: {duration}")
        self.logger.info(f"🌐 URLs processed: {len(company_urls)}")
        self.logger.info(f"✅ Successful: {stats['successful']}")
        self.logger.info(f"❌ Failed: {stats['failed']}")
        self.logger.info(f"💼 New jobs found: {stats['total_jobs']}")
        self.logger.info(f"🎯 Target: Software Engineering in Israel")
        self.logger.info(f"⚡ Rate limiting: {self.batch_size} jobs per batch, {self.write_delay}s delays")
        self.logger.info("=" * 60)

def main():
    """Main entry point with error handling"""
    try:
        scraper = RateLimitedJobScraper()
        scraper.run()
    except KeyboardInterrupt:
        logging.info("⚠️ Interrupted by user")
    except Exception as e:
        logging.error(f"💥 Fatal error: {e}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    main()
'''

with open('job_scraper_v3_1_rate_limited.py', 'w', encoding='utf-8') as f:
    f.write(rate_limited_scraper)

print("✅ Created job_scraper_v3_1_rate_limited.py - Rate-limited batch writing version")