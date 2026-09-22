"""
job_scraper.py -- Automated job listings scraper -> Google Sheets
Reads career page URLs from company_urls.txt, scrapes each for job postings,
filters for Israeli software engineering roles, and saves to Google Sheets.

Tabs:
  Student_Jobs  -- student / intern / trainee positions
  Junior_Jobs   -- entry, junior, graduate, and unclassified roles

Run manually:   python job_scraper.py
Scheduled:      via run_scraper.bat + Windows Task Scheduler
"""

import os
import sys
import json
import time
import html
import re
import hashlib
import socket
import logging
import traceback
import argparse
import subprocess
import signal
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
import gspread
from bs4 import BeautifulSoup, Comment

# -- Optional Selenium --------------------------------------------------------
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# -- Optional undetected-chromedriver -----------------------------------------
try:
    import undetected_chromedriver as uc
    UC_AVAILABLE = True
except ImportError:
    UC_AVAILABLE = False

# -- Optional JobSpy (Indeed integration) -------------------------------------
try:
    from jobspy import scrape_jobs as jobspy_scrape
    JOBSPY_AVAILABLE = True
except ImportError:
    JOBSPY_AVAILABLE = False


# =============================================================================
# Logging
# =============================================================================

def setup_logging(debug: bool = False) -> logging.Logger:
    Path("logs").mkdir(exist_ok=True)
    log_file = Path("logs") / f"job_scraper_{datetime.now().strftime('%Y%m%d')}.log"

    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    for noisy in [
        "urllib3", "selenium", "requests", "gspread", "undetected_chromedriver",
    ]:
        logging.getLogger(noisy).setLevel(logging.ERROR)

    return logging.getLogger("job_scraper")


# Lines matching any of these patterns are stripped from the clean debug file.
_NOISE_PATTERNS = [
    re.compile(r"====== WebDriver manager ======"),
    re.compile(r"Get LATEST chromedriver version"),
    re.compile(r"Driver \[.*\] found in cache"),
    re.compile(r"DevTools listening on ws://"),
    re.compile(r"Exception ignored in:.*Chrome\.__del__"),
    re.compile(r"Traceback \(most recent call last\):"),
    re.compile(r'File ".*undetected_chromedriver.*", line \d+'),
    re.compile(r"self\.quit\(\)"),
    re.compile(r"time\.sleep\(0\.1\)"),
    re.compile(r"OSError: \[WinError 6\]"),
]

def _is_noise(line: str) -> bool:
    s = line.strip()
    return any(p.search(s) for p in _NOISE_PATTERNS)


def write_debug_report(
    debug_path: Path,
    url_results: list,
    log_file: Path,
    run_start: datetime,
    duration,
    sheet_url: str,
):
    """
    Write a clean, human-readable debug report to debug_path.

    url_results status values:
      FAILED   -- could not scrape at all
      NO_JOBS  -- scraped OK, AI found no jobs
      FILTERED -- AI found jobs but all were filtered (senior/non-IL/duplicate/hollow)
      SAVED    -- at least one job written to the sheet
    """
    failed   = [r for r in url_results if r["status"] == "FAILED"]
    no_jobs  = [r for r in url_results if r["status"] == "NO_JOBS"]
    filtered = [r for r in url_results if r["status"] == "FILTERED"]
    saved    = [r for r in url_results if r["status"] == "SAVED"]

    lines = []
    sep  = "=" * 70
    sep2 = "-" * 70

    total_jobs_saved = sum(r.get("jobs_saved", 0) for r in url_results)
    total_jobs_found = sum(r.get("jobs_found", 0) for r in url_results)

    lines += [
        sep,
        f"  JOB SCRAPER DEBUG REPORT",
        f"  Run started : {run_start.strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Duration    : {str(duration).split('.')[0]}",
        f"  Sheet       : {sheet_url}",
        sep,
        "",
        "  URL SUMMARY",
        sep2,
        f"  {'JOBS SAVED':<12} {total_jobs_saved:>3}  -- total new jobs written to sheet",
        f"  {'JOBS FOUND':<12} {total_jobs_found:>3}  -- total raw jobs extracted before filtering",
        sep2,
        f"  {'SAVED':<10} {len(saved):>3}  -- URL sources that produced jobs",
        f"  {'FILTERED':<10} {len(filtered):>3}  -- scraped OK, all jobs rejected (senior/non-IL/duplicate)",
        f"  {'NO_JOBS':<10} {len(no_jobs):>3}  -- scraped OK, AI found nothing",
        f"  {'FAILED':<10} {len(failed):>3}  -- could not scrape (blocked/broken URL)",
        sep2,
        "",
    ]

    if failed:
        lines.append("  !! FAILED URLs  (check / update these in company_urls.txt)")
        lines.append(sep2)
        for r in failed:
            lines.append(f"  {r['url']}")
        lines.append("")

    if filtered:
        lines.append("  ?? FILTERED URLs  (page scraped, but all jobs were rejected)")
        lines.append("     Possible reasons: only senior roles, non-Israel, duplicates.")
        lines.append(sep2)
        for r in filtered:
            lines.append(f"  {r['url']}  [{r['jobs_found']} raw job(s) found, 0 kept]")
        lines.append("")

    if no_jobs:
        lines.append("  -- NO_JOBS URLs  (page loaded, AI extracted nothing)")
        lines.append("     May be a listing page with no matching roles right now,")
        lines.append("     or the URL points to a category/tag page rather than jobs.")
        lines.append(sep2)
        for r in no_jobs:
            lines.append(f"  {r['url']}")
        lines.append("")

    if saved:
        lines.append("  OK SAVED URLs  (produced at least one new job)")
        lines.append(sep2)
        for r in saved:
            s = r["jobs_saved"]
            lines.append(f"  {r['url']}  [{s} job(s) saved]")
        lines.append("")

    lines += [
        sep,
        "  SCRAPE LOG  (noise-filtered)",
        sep,
        "",
    ]

    if log_file.exists():
        raw = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in raw:
            if not _is_noise(line):
                lines.append(line)
    else:
        lines.append("  (log file not found)")

    debug_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# =============================================================================
# Constants / defaults
# =============================================================================

# Pinned Chrome for Testing binaries -- see chrome/README.md for setup.
# These are committed alongside the script so the version is fully controlled
# and immune to silent Chrome auto-updates breaking the scraper overnight.
_CHROME_DIR      = Path(__file__).parent / "chrome"
CHROME_EXE       = str(_CHROME_DIR / "chrome-win64"      / "chrome.exe")
CHROMEDRIVER_EXE = str(_CHROME_DIR / "chromedriver-win64" / "chromedriver.exe")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,he;q=0.8",
}

# Minimum visible body text to consider a page successfully loaded
MIN_CONTENT = 500

# Smart-wait settings for Selenium
JS_SMART_WAIT_MAX   = 25   # max seconds to poll
JS_SMART_WAIT_POLL  = 1    # poll interval seconds
JS_STABLE_ROUNDS    = 3    # consecutive stable polls before declaring ready

# Cloudflare challenge markers
CLOUDFLARE_MARKERS = [
    "just a moment",
    "checking your browser",
    "please wait while we check your browser",
    "enable javascript and cookies",
    "cf-browser-verification",
    "_cf_chl",
]

# LinkedIn blocks headless scrapers categorically - skip silently
BLOCKED_DOMAINS = ["linkedin.com"]

# Domains whose raw HTML is a JS shell -- job content is injected after load.
# These skip straight to Selenium, bypassing the requests tier entirely.
JS_RENDERED_DOMAINS = [
    "myworkdayjobs.com",    # Workday (NVIDIA, Broadcom, Cadence, etc.)
    "phenompeople.com",     # Phenom CMS (MSD/Merck career sites)
    "greenhouse.io",        # Greenhouse ATS
    "lever.co",             # Lever ATS
    "smartrecruiters.com",  # SmartRecruiters
    "taleo.net",            # Oracle Taleo
    "oraclecloud.com",      # Oracle HCM
    "icims.com",            # iCIMS
    "jobvite.com",          # Jobvite
    "successfactors.com",   # SAP SuccessFactors
    "eightfold.ai",         # Eightfold AI (AmEx, etc.)
    "comeet.com",           # Comeet (common in Israeli companies)
    "career.rafael.co.il",  # Rafael career site (JS-rendered)
    "jobs.careers.microsoft.com",  # Microsoft careers SPA (JS-rendered)
]

# Sheet tab names
TAB_STUDENT = "Student_Jobs"
TAB_JUNIOR  = "Junior_Jobs"

# Column order for both tabs
SHEET_COLUMNS = [
    "Date Posted", "Date Added", "Company", "Job Title",
    "Description", "Qualifications", "Location", "URL"
]

# Column widths matching SHEET_COLUMNS order
COL_WIDTHS = [110, 110, 150, 220, 480, 350, 140, 280]

# AI fields that must not all be N/A (job quality gate)
NA_ABORT_THRESHOLD = 3   # abort job entry if this many core fields are N/A

OLLAMA_CONFIG = {
    "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    "model":    os.getenv("OLLAMA_MODEL",    "qwen2.5:7b"),
    "timeout":  int(os.getenv("OLLAMA_TIMEOUT", "180")),
}

# Software engineering role keywords (title matching)
SW_KEYWORDS = {
    "software engineer", "software developer", "developer", "engineer", "programmer",
    "full stack", "fullstack", "frontend", "front-end", "backend", "back-end",
    "web developer", "mobile developer", "ios developer", "android developer",
    "react", "angular", "vue", "node.js", "python developer", "java developer",
    ".net developer", "c# developer", "javascript", "typescript", "golang",
    "kotlin", "swift", "flutter", "react native", "technical lead", "tech lead",
    "cloud", "devops", "sre", "site reliability", "platform engineer",
    "infrastructure engineer", "build engineer", "release engineer",
    "automation engineer", "ci/cd", "qa engineer", "test engineer", "sdet",
    "data engineer", "ml engineer", "machine learning", "ai engineer",
    "embedded software", "firmware", "game developer", "security engineer",
    "student", "intern", "internship", "trainee",  # include student roles explicitly
}

# Israeli city names for location filtering
ISRAELI_CITIES = {
    "jerusalem", "tel aviv", "tel-aviv", "haifa", "petah tikva", "rishon lezion",
    "netanya", "ashdod", "bnei brak", "beersheba", "beer sheva", "holon",
    "ramat gan", "beit shemesh", "ashkelon", "rehovot", "bat yam", "herzliya",
    "hadera", "kfar saba", "modiin", "modi'in", "lod", "raanana", "givatayim",
    "hod hasharon", "or yehuda", "kiryat", "nazareth", "nahariya", "acre",
    "akko", "tiberias", "eilat", "caesarea", "rosh haayin", "nes ziona",
    "yokneam", "karmiel", "safed", "tzfat", "givat shmuel", "ra'anana",
}

# Domains that are Israel-only job boards or career pages.
# Jobs from these sources skip the location check -- the AI often returns N/A
# for location when it isn't displayed inline on the listing page, but for
# these domains we know every posting is Israeli by definition.
ISRAEL_ONLY_DOMAINS = {
    "goozali.com",
    "devjobs.co.il",
    "nortech-platform.com",
}

# Keywords that classify a role as student/intern
STUDENT_KEYWORDS = re.compile(
    r"\b(intern|internship|student|trainee|apprentice)\b", re.IGNORECASE
)

# Keywords that classify a role as entry/junior
JUNIOR_KEYWORDS = re.compile(
    r"\b(entry|junior|graduate|new.?grad|fresh|associate)\b", re.IGNORECASE
)

# Keywords that identify a senior/leadership role -- excluded from Junior_Jobs
SENIOR_KEYWORDS = re.compile(
    r"\b(senior|sr\b|principal|staff|lead|director|manager|head of|architect|vp|chief|distinguished|fellow)\b",
    re.IGNORECASE
)

# ATS platforms where the hiring company name lives in the URL path, not the domain.
# e.g. comeet.com/jobs/blockaid/... -> company = "Blockaid"
ATS_PATH_DOMAINS = {
    "comeet.com", "greenhouse.io", "lever.co", "jobvite.com",
    "smartrecruiters.com", "icims.com", "eightfold.ai",
}


# =============================================================================
# Text / content helpers
# =============================================================================

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_cloudflare_page(text: str) -> bool:
    lowered = text.lower()
    return sum(1 for m in CLOUDFLARE_MARKERS if m in lowered) >= 2


# Fragments that indicate the AI leaked prompt instructions into a field value
_PROMPT_LEAK_RE = re.compile(
    r"(use\s+'?remote'?|n/a\s+if\s+not|if\s+not\s+found|city,\s*country"
    r"|full.?time[,.]?\s*(tel|israel|n/a)|'remote'\s+if\s+remote)",
    re.IGNORECASE,
)

def clean_location(loc: str) -> str:
    """Normalise AI-extracted location strings and strip prompt leakage."""
    if not loc or loc.strip() in ("N/A", ""):
        return "N/A"
    # Strip prompt instructions that leaked into the value
    loc = re.sub(r"\.\s*(Use |'Remote'|N/A\s+if|if\s+remote|if\s+not).*", "", loc, flags=re.IGNORECASE)
    # Normalise "Israel - City" / "Israel – City" → "City, Israel"
    loc = re.sub(r"^Israel\s*[-–]\s*", "", loc)
    # Normalise "City District, Israel" → "City, Israel"
    loc = re.sub(r"\s+District\b", "", loc, flags=re.IGNORECASE)
    loc = loc.strip().strip(".")
    return loc or "N/A"


def clean_field(value: str, field_name: str = "") -> str:
    """Strip prompt leakage from description / qualifications fields."""
    if not value or value.strip() in ("N/A", ""):
        return "N/A"
    if _PROMPT_LEAK_RE.search(value):
        return "N/A"
    return value.strip() or "N/A"


def extract_visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
        tag.decompose()
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()
    return clean_text(soup.get_text(separator=" "))


def create_job_id(title: str, company: str, location: str) -> str:
    """MD5-based dedup key."""
    raw = f"{title}_{company}_{location}".lower().strip()
    raw = re.sub(r"[^a-z0-9_]", "", raw)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def extract_company_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Strip common prefixes iteratively (handles www.careers.philips.com)
        for prefix in ("www.", "careers.", "jobs.", "career.", "apply."):
            if domain.startswith(prefix):
                domain = domain[len(prefix):]
        bare = domain

        # --- ATS platforms: company name is in the URL path, not the domain ---
        if any(ats in bare for ats in ATS_PATH_DOMAINS):
            parts = [p for p in parsed.path.strip("/").split("/") if p]
            # comeet.com/jobs/<company>/...  greenhouse.io/embed/job_board?for=<company>
            candidate = None
            if "for=" in parsed.query:
                m = re.search(r"for=([^&]+)", parsed.query)
                if m:
                    candidate = m.group(1)
            if not candidate and len(parts) >= 2:
                # skip generic path segments like "jobs", "embed", "job_board"
                skip = {"jobs", "embed", "job_board", "careers", "apply", "j", "o"}
                for p in parts:
                    if p.lower() not in skip:
                        candidate = p
                        break
            if candidate:
                return re.sub(r"[-_]", " ", candidate).title()

        # --- Known company mappings ---
        name = bare.split(".")[0]
        known = {
            "microsoft": "Microsoft", "google": "Google", "nvidia": "NVIDIA",
            "apple": "Apple", "intel": "Intel", "amazon": "Amazon",
            "checkpoint": "Check Point", "wix": "Wix", "monday": "monday.com",
            "sentinelone": "SentinelOne", "mobileye": "Mobileye",
            "paloaltonetworks": "Palo Alto Networks", "appsflyer": "AppsFlyer",
            "akamai": "Akamai", "cadence": "Cadence", "qualcomm": "Qualcomm",
            "broadcom": "Broadcom", "ibm": "IBM", "philips": "Philips",
            "dell": "Dell", "cisco": "Cisco", "meta": "Meta", "sap": "SAP",
            "oracle": "Oracle", "hp": "HP", "hpe": "HPE", "amd": "AMD",
            "mobileye": "Mobileye", "radcom": "RADCOM", "radware": "Radware",
            "netsuite": "NetSuite", "nice": "NICE", "amdocs": "Amdocs",
            "harmonicinc": "Harmonic", "cato": "Cato Networks",
            "lightricks": "Lightricks", "snyk": "Snyk", "unity": "Unity",
            "wiz": "Wiz", "hibob": "HiBob", "etoro": "eToro",
            "buildots": "Buildots", "lightrun": "Lightrun", "zafran": "Zafran",
            "ivix": "IVIX", "dragonflydb": "DragonflyDB", "ai21": "AI21 Labs",
            "verbit": "Verbit", "ngsoft": "NGSoft", "elspec": "Elspec",
            "vastdata": "VAST Data", "codevalue": "CodeValue",
            "sentinelone": "SentinelOne", "geberit": "Geberit",
            "edwards": "Edwards", "gehealthcare": "GE HealthCare",
            "odysight": "Odysight", "polytex": "Polytex Technologies",
        }
        return known.get(name, name.title())
    except Exception:
        return "Unknown"


# =============================================================================
# Role classification
# =============================================================================

def is_software_role(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in SW_KEYWORDS)


def is_israeli_location(location: str, source_domain: str = "") -> bool:
    # If the source is a known Israel-only domain, skip the location field
    # entirely -- the AI often returns N/A when location isn't shown inline.
    if source_domain and source_domain in ISRAEL_ONLY_DOMAINS:
        return True
    if not location or not location.strip():
        return False
    loc = location.lower()
    if "israel" in loc or "\u05d9\u05e9\u05e8\u05d0\u05dc" in location:
        return True
    # ", il" / " il" at the end is the ISO-3166-1 alpha-2 code LinkedIn etc. use
    # e.g. "Tel-Aviv, IL" -- safe as a suffix check, won't match "Brazil" etc.
    if loc.endswith(", il") or loc.endswith(" il"):
        return True
    return any(city in loc for city in ISRAELI_CITIES)


def classify_role(title: str) -> str | None:
    """
    Return tab name (TAB_STUDENT or TAB_JUNIOR) or None to reject.

    Logic:
      - Student keywords  → always TAB_STUDENT (even if also 'senior', which is unusual)
      - Senior keywords   → reject (None) -- not a junior role
      - Junior keywords   → TAB_JUNIOR
      - No keywords match → TAB_JUNIOR only if no senior signals; otherwise reject
    """
    if STUDENT_KEYWORDS.search(title):
        return TAB_STUDENT
    if SENIOR_KEYWORDS.search(title):
        return None   # senior/principal/lead/director -- skip
    if JUNIOR_KEYWORDS.search(title):
        return TAB_JUNIOR
    # Unclassified: no junior OR senior signal. Keep in Junior_Jobs as a
    # potential entry-level role (e.g. plain "Software Engineer").
    return TAB_JUNIOR


def is_current_year(date_str: str) -> bool:
    """Return True if date_str contains the current year, or is empty/unknown."""
    if not date_str or date_str.strip() in ("", "N/A", "**PDNA**"):
        return True  # no date = don't discard
    year_match = re.search(r"20(\d{2})", date_str)
    if year_match:
        return int(f"20{year_match.group(1)}") >= datetime.now().year
    return True


# =============================================================================
# Scraping
# =============================================================================

def _build_chrome_options() -> Options:
    opts = Options()
    opts.binary_location = CHROME_EXE
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--ignore-certificate-errors")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(f"--user-agent={HEADERS['User-Agent']}")
    opts.add_argument("--disable-logging")
    opts.add_argument("--log-level=3")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-background-networking")
    opts.add_argument("--disable-features=TranslateUI")
    # Note: excludeSwitches/useAutomationExtension are intentionally omitted --
    # useAutomationExtension was removed in Chrome ~111 and passing it causes
    # Chrome 112+ to exit immediately during session creation.
    opts.add_experimental_option("prefs", {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
    })
    return opts


# Single JS call checking all known ATS job content selectors at once.
# Returns innerText of first matching element with >200 chars, or empty string.
_JOB_SELECTORS_JS = """
(function() {
    var s = [
        '[data-automation-id=\"jobPostingDescription\"]',
        '[data-automation-id=\"job-posting-description\"]',
        '.wd-text',
        '.jdp-description-jobDescription',
        '.jd-info-jobDescription',
        '[class*=\"jobDescription\"]',
        '[class*=\"job-description\"]',
        '#content .job-post',
        '.job-post-content',
        '.posting-description',
        '.content-wrapper .section-wrapper',
        '.co-position-description',
        '.job-description',
        '#job-description',
        '#jobDescription',
        '[itemprop=\"description\"]',
        'article.job'
    ];
    for (var i = 0; i < s.length; i++) {
        var el = document.querySelector(s[i]);
        if (el && el.innerText && el.innerText.trim().length > 200) {
            return el.innerText.trim();
        }
    }
    return '';
})();
"""


def _smart_wait(driver, log: logging.Logger) -> int:
    """
    Poll every JS_SMART_WAIT_POLL seconds for two signals:

    Signal 1 -- Known job element appeared (fast path):
      Fires a single JS call checking all known ATS job content selectors.
      Exits immediately when any selector yields >200 chars. Handles Workday,
      Greenhouse, Lever, Phenom, Oracle HCM, Comeet and generic patterns.

    Signal 2 -- Body text volume stable (fallback):
      For sites not covered by known selectors, waits until body.innerText
      reaches MIN_CONTENT chars and hasn't grown for JS_STABLE_ROUNDS polls.

    Returns final char count.
    """
    elapsed = last_len = stable = 0
    while elapsed < JS_SMART_WAIT_MAX:
        time.sleep(JS_SMART_WAIT_POLL)
        elapsed += JS_SMART_WAIT_POLL
        # Signal 1: known job element check (one JS round-trip)
        # driver.execute_script returns None if the script errors inside the browser
        # so we check the return value rather than catching an exception.
        job_text = driver.execute_script(_JOB_SELECTORS_JS)
        if job_text and len(job_text) > 200:
            log.debug("[smart-wait] Job element detected after %.0fs (%d chars)", elapsed, len(job_text))
            return len(job_text)

        # Signal 2: body text volume + stability
        body = driver.execute_script("return document.body ? document.body.innerText : '';")
        cur = len(body or "")

        log.debug("[smart-wait] %.0fs | %d chars | stable %d/%d", elapsed, cur, stable, JS_STABLE_ROUNDS)
        if cur >= MIN_CONTENT:
            stable = stable + 1 if cur == last_len else 0
            if stable >= JS_STABLE_ROUNDS:
                log.debug("[smart-wait] Stable at %d chars after %.0fs", cur, elapsed)
                return cur
        else:
            stable = 0
        last_len = cur
    log.debug("[smart-wait] Timeout at %d chars", last_len)
    return last_len


def _scroll_page(driver) -> bool:
    """
    Scroll to trigger lazy-loaded content.
    Returns True if scroll succeeded, False if the driver is no longer usable.
    Does not raise -- uses return value so callers can decide what to do.
    """
    result = driver.execute_script("return document.body ? true : false;")
    if not result:
        return False
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(1)
    driver.execute_script("window.scrollTo(0, 0);")
    return True


def _is_js_rendered(url: str) -> bool:
    """Return True if URL belongs to a known JS-rendered ATS platform."""
    url_lower = url.lower()
    return any(domain in url_lower for domain in JS_RENDERED_DOMAINS)


def _is_shell_page(text: str) -> bool:
    """
    Return True if extracted text looks like a page shell rather than real
    job content -- enough chars to pass MIN_CONTENT but no job vocabulary.
    Catches custom-domain ATS sites that serve a JS shell whose navigation
    text alone exceeds the length threshold.
    """
    JOB_VOCAB = [
        "responsibilities", "requirements", "qualifications", "experience",
        "skills", "you will", "we are looking", "what you'll", "what you will",
        "the role", "about the role", "job description", "what we offer",
        "minimum", "preferred", "bachelor", "degree", "years of",
    ]
    text_lower = text.lower()
    return sum(1 for word in JOB_VOCAB if word in text_lower) < 2


def scrape_with_requests(url: str, log: logging.Logger):
    """Fast path. Returns (text, soup, hint) or (None, None, hint)."""
    session = requests.Session()
    session.headers.update(HEADERS)
    for attempt in range(2):
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            if resp.encoding and resp.encoding.lower() in ("latin-1", "iso-8859-1"):
                resp.encoding = resp.apparent_encoding
            if is_cloudflare_page(resp.text):
                log.warning("[requests] Cloudflare detected -- escalating")
                return None, None, None
            soup = BeautifulSoup(resp.text, "html.parser")
            text = extract_visible_text(soup)
            log.debug("[requests] OK -- %d chars", len(text))
            return text, soup, None
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else 0
            if code in (404, 410):
                log.warning("[requests] Dead URL (%d) -- skipping all tiers", code)
                return None, None, "dead"
            if code in (403, 429):
                log.warning("[requests] Bot-blocked (%d) -- skipping Selenium, jumping to UC", code)
                return None, None, "bot"
            log.warning("[requests] HTTP error attempt %d: %s", attempt + 1, e)
        except requests.exceptions.RequestException as e:
            log.warning("[requests] Error attempt %d: %s", attempt + 1, e)
            if attempt == 0:
                time.sleep(1)
    return None, None, None


# ---------------------------------------------------------------------------
# Driver context managers -- guarantee Chrome process cleanup no matter what
# ---------------------------------------------------------------------------

@contextmanager
def _selenium_driver(log: logging.Logger):
    """
    Context manager that creates a Selenium Chrome driver and guarantees
    cleanup at the OS process level, not just at the driver.quit() level.

    The key insight: driver.quit() sends a graceful shutdown signal but can
    fail silently on Windows, especially if the page load is still in progress.
    We track the ChromeDriver PID before yielding, and after the with-block
    exits (for any reason -- normal return, exception, timeout, anything),
    we verify the process is actually gone and force-kill it if not.

    Usage:
        with _selenium_driver(log) as driver:
            if driver is None:
                return None, None   # selenium not available or failed to start
            driver.get(url)
            ...
    """
    if not SELENIUM_AVAILABLE:
        log.warning("[selenium] Not installed")
        yield None
        return

    driver = None
    driver_pid = None

    driver = webdriver.Chrome(service=Service(CHROMEDRIVER_EXE), options=_build_chrome_options())
    # Record the chromedriver PID immediately after launch so we can kill
    # it by PID if quit() fails later.
    driver_pid = driver.service.process.pid if driver.service.process else None

    try:
        yield driver
    finally:
        # Step 1: attempt graceful quit
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass  # expected to sometimes fail -- that's why we have step 2

        # Step 2: verify the chromedriver process is actually dead.
        # If it's still alive, kill it and all its children (Chrome renderers etc.)
        if driver_pid is not None:
            _force_kill_pid(driver_pid, log, label="selenium")

        # Step 3: blanket sweep. chromedriver exiting does not guarantee Chrome's
        # own process tree is gone -- the crashpad-handler subprocess is designed
        # to detach and outlive the browser it monitors, so it (and sometimes the
        # GPU/renderer processes) can survive even a clean driver.quit(). Since
        # driver_pid only ever tracked chromedriver, not chrome.exe itself, this
        # is the only thing that actually catches those survivors.
        kill_orphan_chromes(log)


def _get_chrome_major_version(log: logging.Logger) -> int | None:
    """
    Read the pinned Chrome binary's major version without executing it.
    undetected-chromedriver's own auto-detection doesn't recognise a
    portable binary outside the normal install path and silently falls
    back to a stale hardcoded default ("assuming chrome 108 or higher"),
    which breaks the entire UC tier for any site that reaches it.
    """
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-Item '{CHROME_EXE}').VersionInfo.FileVersion"],
            capture_output=True, text=True, timeout=10,
        )
        return int(result.stdout.strip().split(".")[0])
    except Exception as e:
        log.debug("[uc] Could not read Chrome version: %s", e)
        return None


@contextmanager
def _uc_driver(log: logging.Logger):
    """
    Context manager for undetected-chromedriver. Same guarantee as
    _selenium_driver -- OS-level process cleanup after every use.

    UC is more prone to leaving zombie processes than regular Selenium because
    its stealth patching interferes with Chrome's normal shutdown sequence.
    The force-kill step here is especially important.
    """
    if not UC_AVAILABLE:
        log.warning("[uc] undetected-chromedriver not installed")
        yield None
        return

    driver = None
    driver_pid = None

    opts = uc.ChromeOptions()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")

    driver = uc.Chrome(
        options=opts,
        headless=True,
        driver_executable_path=CHROMEDRIVER_EXE,
        browser_executable_path=CHROME_EXE,
        version_main=_get_chrome_major_version(log),
    )
    driver_pid = driver.service.process.pid if driver.service.process else None

    try:
        yield driver
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

        if driver_pid is not None:
            _force_kill_pid(driver_pid, log, label="uc")

        # Blanket sweep -- see comment in _selenium_driver's finally block.
        kill_orphan_chromes(log)


def _force_kill_pid(pid: int, log: logging.Logger, label: str = "") -> None:
    """
    Kill a process and all its children by PID using taskkill on Windows.
    This is the nuclear option -- it guarantees no orphan Chrome processes
    regardless of what state the driver is in.

    We use taskkill /T (terminate tree) which kills the process AND every
    child process it spawned (Chrome renderers, GPU processes, etc.).

    On non-Windows systems falls back to os.kill with SIGTERM then SIGKILL.
    """
    prefix = f"[{label}] " if label else ""
    try:
        if sys.platform == "win32":
            # /F = force, /T = include child processes, /PID = target by PID
            result = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                log.debug("%sForce-killed driver process tree (PID %d)", prefix, pid)
            else:
                # returncode 128 means the process was already gone -- that's fine
                if b"not found" not in result.stderr.lower() and result.returncode != 128:
                    log.warning("%staskkill returned %d for PID %d", prefix, result.returncode, pid)
        else:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # already dead, which is what we wanted
    except (ProcessLookupError, PermissionError):
        pass  # process already gone -- this is the happy path
    except Exception as e:
        log.warning("%sUnexpected error killing PID %d: %s", prefix, pid, e)


def scrape_with_selenium(url: str, log: logging.Logger):
    """
    Selenium fallback. Returns (text, soup) or (None, None).
    Uses _selenium_driver context manager to guarantee Chrome cleanup.
    Control flow is explicit -- no exceptions used for routing.
    """
    with _selenium_driver(log) as driver:
        if driver is None:
            return None, None

        driver.set_page_load_timeout(30)
        driver.get(url)

        # Wait for body rather than catching TimeoutException
        body_present = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        if not body_present:
            log.warning("[selenium] Body never appeared")
            return None, None

        _scroll_page(driver)
        _smart_wait(driver, log)

        page_html = driver.page_source
        if not page_html or is_cloudflare_page(page_html):
            log.warning("[selenium] Cloudflare detected or empty page -- escalating")
            return None, None

        soup = BeautifulSoup(page_html, "html.parser")
        text = extract_visible_text(soup)
        log.debug("[selenium] OK -- %d chars", len(text))
        return text, soup


def scrape_with_uc(url: str, log: logging.Logger):
    """
    undetected-chromedriver last resort. Returns (text, soup) or (None, None).
    Uses _uc_driver context manager to guarantee Chrome cleanup.
    """
    log.info("[uc] Attempting bypass scrape...")

    with _uc_driver(log) as driver:
        if driver is None:
            return None, None

        driver.set_page_load_timeout(40)
        driver.get(url)
        time.sleep(6)
        _scroll_page(driver)
        _smart_wait(driver, log)

        page_html = driver.page_source
        if not page_html or is_cloudflare_page(page_html):
            log.warning("[uc] Still blocked by Cloudflare")
            return None, None

        soup = BeautifulSoup(page_html, "html.parser")
        text = extract_visible_text(soup)
        log.debug("[uc] OK -- %d chars", len(text))
        return text, soup


def scrape_page(url: str, log: logging.Logger):
    """
    Try requests -> Selenium -> undetected-chromedriver.
    Returns (text, soup) or (None, None).
    """
    domain = urlparse(url).netloc.lower()
    if any(blocked in domain for blocked in BLOCKED_DOMAINS):
        log.warning("[scrape] Skipping blocked domain: %s", domain)
        return None, None

    # Attempt 1 (skipped for known JS-rendered platforms)
    if _is_js_rendered(url):
        log.info("[scrape] Known JS-rendered platform -- skipping requests")
    else:
        text, soup, fail_type = scrape_with_requests(url, log)
        if fail_type == "dead":
            log.warning("[scrape] Hard 404/410 -- aborting all tiers")
            return None, None
        if fail_type == "bot":
            log.info("[scrape] Bot-block detected -- jumping directly to UC")
            text, soup = scrape_with_uc(url, log)
            if text and len(text) >= MIN_CONTENT:
                return text, soup
            return None, None
        if text and len(text) >= MIN_CONTENT:
            if _is_shell_page(text):
                log.info("[scrape] Shell page detected (no job vocabulary) -- escalating to Selenium")
            else:
                return text, soup

    # Attempt 2
    log.info("[scrape] Falling back to Selenium...")
    text, soup = scrape_with_selenium(url, log)
    if text and len(text) >= MIN_CONTENT:
        return text, soup

    # Attempt 3
    log.info("[scrape] Falling back to undetected-chromedriver...")
    text, soup = scrape_with_uc(url, log)
    if text and len(text) >= MIN_CONTENT:
        return text, soup

    return None, None


# =============================================================================
# AI extraction (Ollama / Qwen2.5:7b via HTTP)
# =============================================================================

EXTRACTION_PROMPT = """\
You are a structured job listing extractor. Analyze the career page content below and extract ALL software engineering job postings you can find.

Company hint: {company}
Source URL: {url}

--- PAGE CONTENT ---
{content}
--- END CONTENT ---

Return ONLY a valid JSON object in this exact format -- no preamble, no markdown fences:
{{
  "jobs": [
    {{
      "title": "Exact job title as listed",
      "location": "City, Country. Use 'Remote' if remote. 'N/A' if not found.",
      "description": "1-2 sentence summary of what the role involves.",
      "qualifications": "Key requirements comma-separated. 'N/A' if not found.",
      "date_posted": "Date in YYYY-MM-DD format if listed, otherwise 'N/A'",
      "url": "Direct link to this specific job if available, otherwise use the source URL"
    }}
  ]
}}

Rules:
- Include ONLY software engineering roles (developers, engineers, QA, DevOps, ML, embedded, student/intern tech roles).
- Include ONLY roles based in Israel or with Israeli cities mentioned.
- If you find no qualifying jobs, return {{"jobs": []}}
- For Israeli locations, use common English spellings (Tel Aviv, Haifa, Beer Sheva, Herzliya, Raanana, Netanya, Petah Tikva).
- Do NOT invent jobs that are not clearly listed in the content.
- Output ONLY the JSON object.
"""


def call_ollama(content: str, company: str, url: str, log: logging.Logger):
    """Send scraped content to Ollama and return list of job dicts."""
    prompt = EXTRACTION_PROMPT.format(
        company=company,
        url=url,
        content=content[:8000],
    )

    base_url = OLLAMA_CONFIG["base_url"]
    model    = OLLAMA_CONFIG["model"]
    timeout  = OLLAMA_CONFIG["timeout"]

    log.info("[ai] Analyzing with %s...", model)

    for use_json_fmt in (True, False):
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.05, "top_p": 0.9, "num_predict": 2048},
        }
        if use_json_fmt:
            payload["format"] = "json"

        try:
            resp = requests.post(
                f"{base_url}/api/generate",
                json=payload,
                timeout=timeout,
            )
            if resp.status_code == 500 and use_json_fmt:
                log.debug("[ai] format=json not supported, retrying without...")
                continue
            resp.raise_for_status()
            raw = resp.json().get("response", "")
            if not raw:
                log.error("[ai] Empty response from Ollama")
                return []
            result = _parse_ai_response(raw, log)
            if result is None:
                # JSON was truncated -- retry with double token budget
                if payload["options"]["num_predict"] < 4096:
                    log.warning("[ai] JSON truncated -- retrying with num_predict=4096")
                    payload["options"]["num_predict"] = 4096
                    continue  # re-run the for loop iteration with new payload
                log.error("[ai] JSON parse failed even at 4096 tokens -- skipping")
                return []
            return result

        except requests.exceptions.ConnectionError:
            log.error("[ai] Cannot reach Ollama at %s -- is it running?", base_url)
            return []
        except requests.exceptions.Timeout:
            log.error("[ai] Ollama timed out after %ds", timeout)
            return []
        except requests.exceptions.HTTPError as e:
            log.error("[ai] HTTP error: %s | %s", e, resp.text[:200])
            if not use_json_fmt:
                return []
        except requests.exceptions.RequestException as e:
            log.error("[ai] Request failed: %s", e)
            return []

    return []


def _parse_ai_response(raw: str, log: logging.Logger) -> list:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    # Strip trailing commas before } or ] (common LLM mistake)
    raw = re.sub(r",\s*([}\]])", r"\1", raw)

    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end <= start:
        log.warning("[ai] No JSON found in response")
        return []
    try:
        data = json.loads(raw[start:end])
        jobs = data.get("jobs", [])
        if not isinstance(jobs, list):
            return []
        return jobs
    except json.JSONDecodeError as e:
        log.warning("[ai] JSON parse error: %s", e)
        return None  # None = truncated/malformed; [] = valid empty list


# =============================================================================
# JobSpy / Indeed integration
# =============================================================================

JOBSPY_CONFIG = {
    # Search terms shared by Indeed, LinkedIn, Glassdoor, and Bayt.
    "search_terms": {
        TAB_STUDENT: "software engineer intern",
        TAB_JUNIOR:  "junior software engineer",
    },
    # Google Jobs needs its own freeform search string -- be very specific
    # or it returns globally-mixed results.
    "google_search_terms": {
        TAB_STUDENT: "software engineer intern Israel Tel Aviv",
        TAB_JUNIOR:  "junior software engineer Israel Tel Aviv",
    },
    "location":       "Israel",
    "country_indeed": "Israel",
    "results_wanted": 30,   # per site per search term
    "hours_old":      168,  # last 7 days

    # Sites to query. ZipRecruiter excluded -- US-only inventory.
    # linkedin_fetch_description fetches full descriptions (slower but worth it).
    "sites":          ["indeed", "linkedin"],  # glassdoor=API auth required, bayt=403 on IL IP, google=no IL results
}


def _jobspy_row_to_job(row) -> dict:
    """
    Convert a single JobSpy DataFrame row (pandas Series) into the dict
    format expected by filter_jobs().
    """
    import pandas as pd

    def safe(val, fallback="N/A"):
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return fallback
        return str(val).strip() or fallback

    # Location: prefer city, fall back to country
    city    = safe(getattr(row, "city",    None), "")
    country = safe(getattr(row, "country", None), "")
    if city and country:
        location = f"{city}, {country}"
    elif city:
        location = city
    elif country:
        location = country
    else:
        location = "Israel"

    # Normalise date to YYYY-MM-DD
    date_posted = safe(getattr(row, "date_posted", None))
    if date_posted and date_posted != "N/A":
        try:
            import datetime as dt
            if hasattr(date_posted, "strftime"):
                date_posted = date_posted.strftime("%Y-%m-%d")
            else:
                parsed = dt.datetime.strptime(str(date_posted)[:10], "%Y-%m-%d")
                date_posted = parsed.strftime("%Y-%m-%d")
        except Exception:
            pass

    return {
        "title":          safe(getattr(row, "title",       None)),
        "company":        safe(getattr(row, "company",     None)),
        "location":       location,
        "description":    safe(getattr(row, "description", None)),
        "qualifications": "N/A",
        "date_posted":    date_posted,
        "url":            safe(getattr(row, "job_url",     None)),
    }


def _jobspy_call(site: str, search_term: str, google_search_term: str,
                 log: logging.Logger):
    """
    Run a single JobSpy scrape for one site + search term.
    Returns a DataFrame or None.
    """
    import warnings
    kwargs = dict(
        site_name          = [site],
        search_term        = search_term,
        location           = JOBSPY_CONFIG["location"],
        results_wanted     = JOBSPY_CONFIG["results_wanted"],
        hours_old          = JOBSPY_CONFIG["hours_old"],
        description_format = "markdown",
    )

    if site == "indeed":
        kwargs["country_indeed"] = JOBSPY_CONFIG["country_indeed"]

    if site == "linkedin":
        # Fetch full descriptions -- slower but gives qualifications text
        kwargs["linkedin_fetch_description"] = True

    if site == "google":
        # Google ignores search_term and uses only google_search_term
        kwargs["google_search_term"] = google_search_term

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return jobspy_scrape(**kwargs)
    except Exception as e:
        log.error("[jobspy] %s search failed for %r: %s", site.capitalize(), search_term, e)
        return None


def run_jobspy(log: logging.Logger) -> list:
    """
    Run JobSpy searches across Indeed, LinkedIn, Glassdoor, Google, and Bayt
    for Israeli software engineering roles.
    Returns a flat list of job dicts in filter_jobs() format.
    """
    if not JOBSPY_AVAILABLE:
        log.warning("[jobspy] python-jobspy not installed -- skipping (pip install python-jobspy)")
        return []

    all_jobs = []
    sites    = JOBSPY_CONFIG["sites"]

    for tab, term in JOBSPY_CONFIG["search_terms"].items():
        google_term = JOBSPY_CONFIG["google_search_terms"][tab]

        for site in sites:
            log.info("[jobspy] %s: searching %r ...", site.capitalize(), term)
            df = _jobspy_call(site, term, google_term, log)

            if df is None or df.empty:
                log.info("[jobspy]   No results")
                continue

            log.info("[jobspy]   %d raw results", len(df))
            for _, row in df.iterrows():
                all_jobs.append(_jobspy_row_to_job(row))

    log.info("[jobspy] Total raw jobs across all sites: %d", len(all_jobs))
    return all_jobs


# =============================================================================
# Filtering & deduplication
# =============================================================================

def filter_jobs(jobs: list, existing_ids: set, log: logging.Logger, source_url: str = "") -> dict:
    """
    Filter raw AI output. Returns {"Student_Jobs": [...], "Junior_Jobs": [...]}.
    """
    results = {TAB_STUDENT: [], TAB_JUNIOR: []}
    source_domain = urlparse(source_url).netloc.removeprefix("www.") if source_url else ""

    for job in jobs:
        title    = str(job.get("title", "")).strip()
        location = clean_location(str(job.get("location", "")).strip())
        company  = str(job.get("company", "")).strip()

        if not title:
            continue

        if not is_software_role(title):
            log.info("[filter] SKIP non-SW:     %s", title)
            continue

        # Classify first -- rejects senior/principal/lead/director roles
        tab = classify_role(title)
        if tab is None:
            log.info("[filter] SKIP senior/lead: %s", title)
            continue

        if not is_israeli_location(location, source_domain):
            log.info("[filter] SKIP non-IL:     %s | %s", title, location)
            continue

        date_posted = str(job.get("date_posted", "")).strip()
        if not is_current_year(date_posted):
            log.debug("[filter] Skipping old posting: %s | %s", title, date_posted)
            continue

        job_id = create_job_id(title, company, location)
        if job_id in existing_ids:
            log.debug("[filter] Duplicate: %s @ %s", title, company)
            continue

        description    = clean_field(str(job.get("description",    "N/A")), "description")
        qualifications = clean_field(str(job.get("qualifications", "N/A")), "qualifications")

        # Quality gate: skip hollow entries with no useful content at all
        if description == "N/A" and qualifications == "N/A":
            log.debug("[filter] Skipping hollow job (no description or qualifications): %s @ %s", title, company)
            # Still save if we at least have a direct job URL (title + URL is useful)
            job_url = str(job.get("url", "")).strip()
            if not job_url or job_url == str(job.get("source_url", "")):
                continue

        existing_ids.add(job_id)

        results[tab].append({
            "date_posted":    date_posted or "N/A",
            "date_added":     datetime.now().strftime("%Y-%m-%d"),
            "company":        company or "N/A",
            "title":          title,
            "description":    description,
            "qualifications": qualifications,
            "location":       location,
            "url":            str(job.get("url", "")).strip(),
        })

    return results


# =============================================================================
# Google Sheets
# =============================================================================

def _get_gc() -> gspread.Client:
    creds_path = os.getenv("GOOGLE_SHEETS_CREDS")
    if not creds_path:
        raise RuntimeError("GOOGLE_SHEETS_CREDS environment variable not set")
    if not os.path.isfile(creds_path):
        raise RuntimeError(f"Credentials file not found: {creds_path}")
    return gspread.service_account(creds_path)


def _open_spreadsheet(gc: gspread.Client, sheet_ref: str):
    """Open by URL, key, or name."""
    if sheet_ref.startswith("http"):
        return gc.open_by_url(sheet_ref)
    if len(sheet_ref) > 25 and "/" not in sheet_ref:
        return gc.open_by_key(sheet_ref)
    return gc.open(sheet_ref)


def _get_or_create_tab(spreadsheet, tab_name: str, log: logging.Logger):
    """Return existing tab or create with headers + formatting."""
    try:
        ws = spreadsheet.worksheet(tab_name)
        log.info("[sheets] Using existing tab: %s", tab_name)
        # Add headers if empty
        if not ws.row_values(1):
            ws.append_row(SHEET_COLUMNS)
            _format_header(ws, log)
        return ws
    except gspread.exceptions.WorksheetNotFound:
        log.info("[sheets] Creating tab: %s", tab_name)
        ws = spreadsheet.add_worksheet(title=tab_name, rows=2000, cols=len(SHEET_COLUMNS))
        ws.append_row(SHEET_COLUMNS)
        _format_header(ws, log)
        return ws


def _format_header(ws, log: logging.Logger):
    """Bold header row, freeze, set column widths -- single batch_update call."""
    try:
        n_cols = len(SHEET_COLUMNS)
        dim_requests = [
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": ws.id, "dimension": "COLUMNS",
                        "startIndex": i, "endIndex": i + 1,
                    },
                    "properties": {"pixelSize": w},
                    "fields": "pixelSize",
                }
            }
            for i, w in enumerate(COL_WIDTHS)
        ]
        freeze = {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": ws.id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        }
        ws.spreadsheet.batch_update({"requests": dim_requests + [freeze]})

        col_letter = chr(ord("A") + n_cols - 1)
        ws.format(f"A1:{col_letter}1", {
            "backgroundColor": {"red": 0.78, "green": 0.78, "blue": 0.78},
            "textFormat": {"bold": True, "fontSize": 11},
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
        })
    except Exception as e:
        log.warning("[sheets] Header formatting failed: %s", e)


def _build_row_format_requests(ws, row_number: int) -> list:
    """Return the batch_update request dicts for a single data row (does NOT call API)."""
    row_idx    = row_number - 1
    url_col_idx = SHEET_COLUMNS.index("URL")
    n_cols     = len(SHEET_COLUMNS)

    return [
        # All columns: wrap
        {
            "repeatCell": {
                "range": {
                    "sheetId": ws.id,
                    "startRowIndex": row_idx, "endRowIndex": row_number,
                    "startColumnIndex": 0, "endColumnIndex": n_cols,
                },
                "cell": {"userEnteredFormat": {
                    "wrapStrategy": "WRAP",
                    "verticalAlignment": "TOP",
                    "textFormat": {"fontSize": 10},
                }},
                "fields": "userEnteredFormat(wrapStrategy,verticalAlignment,textFormat)",
            }
        },
        # URL column: clip instead of wrap
        {
            "repeatCell": {
                "range": {
                    "sheetId": ws.id,
                    "startRowIndex": row_idx, "endRowIndex": row_number,
                    "startColumnIndex": url_col_idx, "endColumnIndex": url_col_idx + 1,
                },
                "cell": {"userEnteredFormat": {
                    "wrapStrategy": "CLIP",
                    "verticalAlignment": "TOP",
                    "textFormat": {"fontSize": 9},
                }},
                "fields": "userEnteredFormat(wrapStrategy,verticalAlignment,textFormat)",
            }
        },
        # Row height cap
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": ws.id, "dimension": "ROWS",
                    "startIndex": row_idx, "endIndex": row_number,
                },
                "properties": {"pixelSize": 120},
                "fields": "pixelSize",
            }
        },
    ]


def _format_data_row(ws, row_number: int, log: logging.Logger):
    """Format a single data row (kept for backward-compat; prefer batching)."""
    try:
        ws.spreadsheet.batch_update({"requests": _build_row_format_requests(ws, row_number)})
    except Exception as e:
        log.warning("[sheets] Row formatting failed: %s", e)


def load_existing_ids(worksheets: dict, log: logging.Logger) -> set:
    """
    Load existing job IDs from both tabs to prevent duplicates.
    Reads Title (col 4), Company (col 3), Location (col 7) -- 1-based.
    """
    existing = set()
    col_map = {
        "title":    SHEET_COLUMNS.index("Job Title") + 1,
        "company":  SHEET_COLUMNS.index("Company") + 1,
        "location": SHEET_COLUMNS.index("Location") + 1,
    }
    for tab_name, ws in worksheets.items():
        try:
            all_rows = ws.get_all_values()
            for row in all_rows[1:]:  # skip header
                title    = row[col_map["title"] - 1]    if len(row) >= col_map["title"]    else ""
                company  = row[col_map["company"] - 1]  if len(row) >= col_map["company"]  else ""
                location = row[col_map["location"] - 1] if len(row) >= col_map["location"] else ""
                if title and company:
                    existing.add(create_job_id(title, company, location))
        except Exception as e:
            log.warning("[sheets] Could not load existing jobs from %s: %s", tab_name, e)
    log.info("[sheets] Loaded %d existing job IDs", len(existing))
    return existing


def save_jobs_to_tab(ws, jobs: list, tab_name: str, log: logging.Logger):
    """Insert new jobs at the top of a tab (row 2, right after the header) in batches,
    so the sheet always reads newest-to-oldest, then format all new rows in ONE batch_update call."""
    if not jobs:
        return

    log.info("[sheets] Saving %d jobs to %s...", len(jobs), tab_name)
    key_order = ["date_posted", "date_added", "company", "title",
                 "description", "qualifications", "location", "url"]
    rows = [[job.get(k, "") for k in key_order] for job in jobs]

    # --- Step 1: insert all data rows at row 2, in batches, with rate-limit retry ---
    # Batches are inserted in REVERSE order so the final on-sheet order (top to bottom)
    # still matches `rows`' original order, sitting as one block above the existing rows.
    BATCH = 10
    batches = [rows[i:i + BATCH] for i in range(0, len(rows), BATCH)]
    for idx, batch in enumerate(reversed(batches)):
        for attempt in range(3):
            try:
                ws.insert_rows(batch, row=2, value_input_option="RAW")
                break
            except gspread.exceptions.APIError as e:
                if "429" in str(e):
                    wait = 30 if attempt > 0 else 15
                    log.warning("[sheets] Rate limit hit -- waiting %ds...", wait)
                    time.sleep(wait)
                else:
                    log.error("[sheets] API error: %s", e)
                    break
            except Exception as e:
                log.error("[sheets] Write error: %s", e)
                if attempt < 2:
                    time.sleep(5)

        if idx + 1 < len(batches):
            time.sleep(2)  # gentle pacing between batches

    # --- Step 2: format ALL new rows (row 2 .. 2+len(rows)-1) in a SINGLE batch_update call ---
    if rows:
        all_format_reqs = []
        for offset in range(len(rows)):
            all_format_reqs.extend(_build_row_format_requests(ws, 2 + offset))
        try:
            # Split into chunks of 100 requests to stay within API limits
            CHUNK = 100
            for i in range(0, len(all_format_reqs), CHUNK):
                ws.spreadsheet.batch_update({"requests": all_format_reqs[i:i + CHUNK]})
                if i + CHUNK < len(all_format_reqs):
                    time.sleep(2)
        except Exception as e:
            log.warning("[sheets] Batch row formatting failed: %s", e)

    log.info("[sheets] Done saving to %s", tab_name)


# =============================================================================
# URL loading
# =============================================================================

def load_urls(urls_file: str, log: logging.Logger) -> list:
    path = Path(urls_file)
    if not path.exists():
        # Create sample file
        path.write_text(
            "# Add career page URLs here, one per line\n"
            "# Lines starting with # are ignored\n",
            encoding="utf-8"
        )
        log.warning("[urls] %s not found -- created empty template", urls_file)
        return []

    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            # Skip obviously non-job URLs
            if "docs.google.com/spreadsheets" in line:
                log.debug("[urls] Skipping Google Sheets URL: %s", line[:60])
                continue
            urls.append(line)

    log.info("[urls] Loaded %d URLs", len(urls))
    return urls


# =============================================================================
# Main
# =============================================================================

def kill_orphan_chromes(log: logging.Logger) -> None:
    """
    Kill any Chrome or ChromeDriver processes left over from previous runs
    before we start a new one. This is a safety net for the case where the
    script was interrupted mid-run (Ctrl+C, crash, Task Scheduler kill, etc.)
    and the context managers didn't get a chance to clean up.

    Only kills processes owned by the current user to avoid touching
    other users' Chrome sessions on a shared machine.
    """
    if sys.platform != "win32":
        return  # taskkill is Windows-only; on Linux pkill would be used instead

    targets = ("chrome.exe", "chromedriver.exe")
    killed = 0
    for name in targets:
        result = subprocess.run(
            ["taskkill", "/F", "/IM", name, "/T"],
            capture_output=True,
            timeout=10,
        )
        # returncode 128 = "process not found" -- that's fine, nothing to kill
        if result.returncode == 0:
            killed += 1
    if killed:
        log.info("[startup] Cleaned up orphan Chrome processes from previous run")
        time.sleep(1)  # brief pause to let OS fully release ports/handles


def main():
    parser = argparse.ArgumentParser(description="Automated job listings scraper -> Google Sheets")
    parser.add_argument("--sheet", default="job-scrapper",
                        help="Google Sheet name or URL (default: job-scrapper)")
    parser.add_argument("--urls", default="company_urls.txt",
                        help="Path to URLs file (default: company_urls.txt)")
    parser.add_argument("--model", default=None,
                        help="Ollama model override (default: qwen2.5:7b)")
    parser.add_argument("--debug", action="store_true", help="Verbose debug output")
    parser.add_argument("--no-jobspy", action="store_true",
                        help="Skip Indeed/JobSpy search (run company URLs only)")
    args = parser.parse_args()

    log = setup_logging(args.debug)

    # Kill any orphan Chrome/ChromeDriver processes from a previous interrupted run
    kill_orphan_chromes(log)

    if args.model:
        OLLAMA_CONFIG["model"] = args.model

    print("=" * 60)
    print("  Job Scraper -- Qwen2.5:7b + Google Sheets")
    print("=" * 60)

    # -- 1. Ollama check -------------------------------------------------------
    log.info("[startup] Checking Ollama connection...")
    try:
        resp = requests.get(f"{OLLAMA_CONFIG['base_url']}/api/tags", timeout=5)
        resp.raise_for_status()
        log.info("[startup] Ollama OK")
    except Exception:
        log.error("[startup] Cannot reach Ollama at %s", OLLAMA_CONFIG["base_url"])
        log.error("  Run: ollama serve")
        log.error("  Then: ollama pull %s", OLLAMA_CONFIG["model"])
        sys.exit(1)

    # -- 2. Google Sheets ------------------------------------------------------
    log.info("[startup] Connecting to Google Sheets...")
    try:
        gc = _get_gc()
        spreadsheet = _open_spreadsheet(gc, args.sheet)
        ws_student = _get_or_create_tab(spreadsheet, TAB_STUDENT, log)
        ws_junior  = _get_or_create_tab(spreadsheet, TAB_JUNIOR,  log)
        sheet_url  = spreadsheet.url
        log.info("[startup] Sheet ready: %s", sheet_url)
    except Exception as e:
        log.error("[startup] Google Sheets error: %s", e)
        sys.exit(1)

    worksheets = {TAB_STUDENT: ws_student, TAB_JUNIOR: ws_junior}

    # -- 3. Load existing job IDs for deduplication ----------------------------
    existing_ids = load_existing_ids(worksheets, log)

    # -- 4. Load URLs ----------------------------------------------------------
    urls = load_urls(args.urls, log)
    if not urls:
        log.error("[startup] No URLs to scrape. Add URLs to %s", args.urls)
        sys.exit(1)

    # -- 5. JobSpy / Indeed search ---------------------------------------------
    start_time = datetime.now()
    all_new = {TAB_STUDENT: [], TAB_JUNIOR: []}
    failed_urls = []
    url_results = []

    if not getattr(args, "no_jobspy", False):
        jobspy_jobs = run_jobspy(log)
        if jobspy_jobs:
            for job in jobspy_jobs:
                if not job.get("company"):
                    job["company"] = "N/A"
            jobspy_categorized = filter_jobs(jobspy_jobs, existing_ids, log)
            n_student = len(jobspy_categorized[TAB_STUDENT])
            n_junior  = len(jobspy_categorized[TAB_JUNIOR])
            n_saved   = n_student + n_junior
            log.info("[jobspy] Kept after filtering: %d student, %d junior", n_student, n_junior)
            all_new[TAB_STUDENT].extend(jobspy_categorized[TAB_STUDENT])
            all_new[TAB_JUNIOR].extend(jobspy_categorized[TAB_JUNIOR])
            url_results.append({
                "url":        "JobSpy (Indeed/LinkedIn/Glassdoor/Google/Bayt)",
                "status":     "SAVED" if n_saved > 0 else "FILTERED",
                "jobs_found": len(jobspy_jobs),
                "jobs_saved": n_saved,
            })
    else:
        log.info("[jobspy] Skipped (--no-jobspy)")

    # -- 6. Company URL scrape loop --------------------------------------------

    def _dns_ok(url: str) -> bool:
        """Quick DNS pre-check to skip URLs whose host doesn't resolve."""
        try:
            host = urlparse(url).netloc.split(":")[0]
            socket.getaddrinfo(host, None)
            return True
        except socket.gaierror:
            return False

    for i, url in enumerate(urls, 1):
        if not _dns_ok(url):
            log.warning("[dns] Cannot resolve host -- skipping: %s", urlparse(url).netloc)
            url_results.append({"url": url, "status": "FAILED", "jobs_found": 0, "jobs_saved": 0})
            continue
        domain = urlparse(url).netloc
        log.info("[%d/%d] %s", i, len(urls), domain)

        try:
            text, soup = scrape_page(url, log)
            if not text:
                log.warning("  Could not scrape -- skipping")
                failed_urls.append(url)
                url_results.append({"url": url, "status": "FAILED", "jobs_found": 0, "jobs_saved": 0})
                continue

            company = extract_company_from_url(url)
            raw_jobs = call_ollama(text, company, url, log)

            if not raw_jobs:
                log.info("  No jobs extracted from this page")
                url_results.append({"url": url, "status": "NO_JOBS", "jobs_found": 0, "jobs_saved": 0})
            else:
                # Inject company name into each job before filtering
                for job in raw_jobs:
                    if not job.get("company"):
                        job["company"] = company

                categorized = filter_jobs(raw_jobs, existing_ids, log, source_url=url)
                n_student = len(categorized[TAB_STUDENT])
                n_junior  = len(categorized[TAB_JUNIOR])
                n_saved   = n_student + n_junior
                log.info("  Found: %d student, %d junior", n_student, n_junior)
                all_new[TAB_STUDENT].extend(categorized[TAB_STUDENT])
                all_new[TAB_JUNIOR].extend(categorized[TAB_JUNIOR])

                if n_saved > 0:
                    url_results.append({"url": url, "status": "SAVED",    "jobs_found": len(raw_jobs), "jobs_saved": n_saved})
                else:
                    url_results.append({"url": url, "status": "FILTERED", "jobs_found": len(raw_jobs), "jobs_saved": 0})

        except Exception as e:
            log.error("  Unexpected error: %s", e)
            if args.debug:
                log.debug(traceback.format_exc())
            failed_urls.append(url)
            url_results.append({"url": url, "status": "FAILED", "jobs_found": 0, "jobs_saved": 0})

        # Polite delay between sites
        if i < len(urls):
            time.sleep(3)

    # -- 8. Save to Sheets -----------------------------------------------------
    save_jobs_to_tab(ws_student, all_new[TAB_STUDENT], TAB_STUDENT, log)
    save_jobs_to_tab(ws_junior,  all_new[TAB_JUNIOR],  TAB_JUNIOR,  log)

    # -- 9. Summary ------------------------------------------------------------
    duration = datetime.now() - start_time
    total = len(all_new[TAB_STUDENT]) + len(all_new[TAB_JUNIOR])

    jobspy_result = next((r for r in url_results if r["url"].startswith("JobSpy")), None)

    print("\n" + "=" * 60)
    print("  COMPLETED")
    print("=" * 60)
    print(f"  Duration:       {str(duration).split('.')[0]}")
    if jobspy_result:
        print(f"  JobSpy:          {jobspy_result['jobs_saved']} saved "
              f"({jobspy_result['jobs_found']} raw)")
    print(f"  URLs scraped:   {len(urls) - len(failed_urls)}/{len(urls)}")
    print(f"  New jobs saved: {total} ({len(all_new[TAB_STUDENT])} student, {len(all_new[TAB_JUNIOR])} junior)")
    if failed_urls:
        print(f"  Failed URLs:    {len(failed_urls)}")
        for u in failed_urls:
            print(f"    - {u}")
    print(f"  Sheet: {sheet_url}")
    print("=" * 60)

    # -- 10. Write clean debug report -------------------------------------------
    debug_dir  = Path("debug")
    debug_dir.mkdir(exist_ok=True)
    debug_file = debug_dir / f"debug_{start_time.strftime('%Y%m%d_%H%M')}.txt"
    log_file   = Path("logs") / f"job_scraper_{start_time.strftime('%Y%m%d')}.log"
    write_debug_report(debug_file, url_results, log_file, start_time, duration, sheet_url)
    print(f"  Debug report:   {debug_file}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)
    except Exception:
        logging.getLogger("job_scraper").error("Unexpected error:\n%s", traceback.format_exc())
        sys.exit(1)
