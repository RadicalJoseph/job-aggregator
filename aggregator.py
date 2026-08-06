# aggregator.py
import os
import re
import logging
import requests
import sys
import pandas as pd
from datetime import datetime
from typing import Optional, Tuple
from database import init_db, record_job
from jobspy import scrape_jobs
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

def extract_company_name(job_payload: dict, fallback: str) -> str:
    """Best-effort extraction of the hiring company from the source payload."""
    if not isinstance(job_payload, dict):
        return fallback

    for key in ("companyName", "company", "employer", "organization", "hiringCompany"):
        value = job_payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    nested = job_payload.get("company")
    if isinstance(nested, dict):
        for key in ("name", "companyName", "title"):
            value = nested.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return fallback

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

LOG_FILE = os.path.join(DATA_DIR, "aggregator.log")
REFRESH_SIGNAL_PATH = os.path.join(DATA_DIR, "refresh.signal")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)

TARGET_ROLE_PATTERNS = [
    r"\btechnical analyst\b", r"\btech analyst\b", r"\bbusiness analyst\b",
    r"\bsoftware analyst\b", r"\btechnical writer\b", r"\bsystems analyst\b",
    r"\batlassian administrator\b", r"\bjira administrator\b", r"\bitsm specialist\b",
    r"\bai enablement\b", r"\bai\b", r"\btechnology\b", r"\btechnical\b",
    r"\bdirector\b", r"\bmanager\b", r"\blead\b", r"\bspecialist\b",
    r"\bprogram manager\b", r"\bknowledge management\b", r"\bknowledge mgmt\b"
]

GREENHOUSE_BOARDS = {
    "atlassian": "Atlassian", "scaleai": "Scale AI", "cloverhealth": "Clover Health",
    "canonical": "Canonical", "github": "GitHub", "hiringcafe": "Hiring Cafe", "writefolks": "WriteFolks"
}

ASHBY_BOARDS = {"harvey": "Harvey", "firecrawl": "Firecrawl"}
LEVER_BOARDS = {"netflix": "Netflix"}

CONSERVATION_ENVIRONMENTAL_TARGETS = [
    "Climatebase", "Conservation International (CI)", "Conservation Job Board",
    "Environmental Defense Fund (EDF)", "Green Jobs Network", "Land Trust Alliance Job Board",
    "Maine Coast Heritage Trust (MCHT)", "National Audubon Society", "Natural Resources Council (NRC)",
    "Natural Resources Defense Council (NRDC)", "Society for Conservation Biology Job Board",
    "The Conservation Fund", "Wildlife Conservation Society (WCS)", "World Resources Institute (WRI)",
    "World Wildlife Fund (WWF)", "Idealist"
]

MIN_CONSERVATION_SALARY = 80000

# Proxy definition for JobSpy. Replace with valid credentials to bypass Glassdoor/Indeed 400 errors.
PROXIES = ["http://user:pass@host:port", "http://user:pass@host2:port"]

def matches_target_role(title: str) -> bool:
    for pattern in TARGET_ROLE_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            return True
    return False

def parse_salary_floor(text: str) -> Optional[int]:
    if not text: return None
    k_matches = re.findall(r'\$?\s*(\d{2,3})\s*k\b', text, re.IGNORECASE)
    if k_matches: return int(k_matches[0]) * 1000
    full_num_matches = re.findall(r'\$\s*(\d{2,3},\d{3})', text)
    if full_num_matches: return int(full_num_matches[0].replace(",", ""))
    return None

def evaluate_salary(company_or_source: str, text: str) -> Tuple[bool, str]:
    """Parses salary and enforces a global minimum threshold."""
    floor = parse_salary_floor(text)
    salary_str = f"${floor:,}" if floor else "Unspecified"

    if floor is not None and floor < MIN_CONSERVATION_SALARY:
        return (False, salary_str)
        
    return (True, salary_str)

def is_recent_enough(posted_at: Optional[str]) -> bool:
    """Evaluates if a parsed date string falls within the last 7 days."""
    if not posted_at:
        return True 
    
    try:
        dt = pd.to_datetime(posted_at, utc=True)
        cutoff = pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=7)
        return dt >= cutoff
    except Exception as e:
        logging.debug(f"Date parsing failed for '{posted_at}': {e}")
        return True 

def extract_posted_at(job_payload: dict) -> Optional[str]:
    """Best-effort extraction of a source-provided posting date from nested payloads."""
    if not isinstance(job_payload, dict):
        return None

    candidates = []

    def walk(value):
        if isinstance(value, dict):
            for key, nested_value in value.items():
                lowered = key.lower()
                if lowered in {"postedat", "posted_at", "createdat", "dateposted", "publishedat", "updatedat", "lastupdated"}:
                    if nested_value:
                        candidates.append(str(nested_value))
                elif isinstance(nested_value, (dict, list)):
                    walk(nested_value)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(job_payload)

    for key in ("postedAt", "posted_at", "createdAt", "datePosted", "publishedAt", "updatedAt", "lastUpdated"):
        if key in job_payload:
            value = job_payload.get(key)
            if value:
                return str(value)

    for value in candidates:
        if value:
            return value

    return None

def process_greenhouse_boards() -> int:
    new_jobs = 0
    for board_token, display_name in GREENHOUSE_BOARDS.items():
        try:
            res = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true", timeout=12)
            if res.status_code == 200:
                for job in res.json().get("jobs", []):
                    title = job.get("title", "")
                    if matches_target_role(title):
                        url, loc, content = job.get("absolute_url", ""), job.get("location", {}).get("name", "Remote"), job.get("content", "")
                        is_valid, sal_str = evaluate_salary(display_name, content)
                        posted_at = extract_posted_at(job)
                        company_name = extract_company_name(job, display_name)
                        if is_valid and is_recent_enough(posted_at) and record_job(url, title, company_name, "Greenhouse API", loc, sal_str, posted_at):
                            logging.info(f"[NEW] {display_name}: {title} -> {url}")
                            new_jobs += 1
        except Exception as e: logging.error(f"Error {display_name}: {e}")
    return new_jobs

def process_ashby_boards() -> int:
    new_jobs = 0
    for board_token, display_name in ASHBY_BOARDS.items():
        try:
            res = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{board_token}", timeout=12)
            if res.status_code == 200:
                for job in res.json().get("jobs", []):
                    title = job.get("title", "")
                    if matches_target_role(title):
                        url, loc = job.get("jobUrl", ""), job.get("locationName", "Remote")
                        is_valid, sal_str = evaluate_salary(display_name, str(job))
                        posted_at = extract_posted_at(job)
                        company_name = extract_company_name(job, display_name)
                        if is_valid and is_recent_enough(posted_at) and record_job(url, title, company_name, "Ashby API", loc, sal_str, posted_at):
                            logging.info(f"[NEW] {display_name}: {title} -> {url}")
                            new_jobs += 1
        except Exception as e: logging.error(f"Error {display_name}: {e}")
    return new_jobs

def process_lever_boards() -> int:
    new_jobs = 0
    for board_token, display_name in LEVER_BOARDS.items():
        try:
            res = requests.get(f"https://api.lever.co/v0/postings/{board_token}?mode=json", timeout=12)
            if res.status_code == 200:
                for job in res.json():
                    title = job.get("text", "")
                    if matches_target_role(title):
                        url, loc = job.get("hostedUrl", ""), job.get("categories", {}).get("location", "Remote")
                        is_valid, sal_str = evaluate_salary(display_name, job.get("descriptionPlain", ""))
                        posted_at = extract_posted_at(job)
                        company_name = extract_company_name(job, display_name)
                        if is_valid and is_recent_enough(posted_at) and record_job(url, title, company_name, "Lever API", loc, sal_str, posted_at):
                            logging.info(f"[NEW] {display_name}: {title} -> {url}")
                            new_jobs += 1
        except Exception as e: logging.error(f"Error {display_name}: {e}")
    return new_jobs

def process_jobspy_boards() -> int:
    """
    Executes concurrent scraping across multiple platforms including Google Jobs, ZipRecruiter, and Glassdoor.
    Splits queries to explicitly target US-based Remote roles 
    and local roles within a 100-mile radius of Yarmouth, ME.
    Restricts results to established conservation targets.
    """
    new_jobs = 0
    search_terms = ["Atlassian Administrator", "Technical Writer", "Knowledge Management", "Systems Analyst"]
    
    for term in search_terms:
        try:
            df_remote = scrape_jobs(
                site_name=["linkedin", "indeed", "google", "zip_recruiter", "glassdoor"],
                search_term=term,
                location="United States",
                is_remote=True,
                results_wanted=15,
                proxies=PROXIES
            )
            
            df_local = scrape_jobs(
                site_name=["linkedin", "indeed", "google", "zip_recruiter", "glassdoor"],
                search_term=term,
                location="Yarmouth, ME",
                distance=100,
                results_wanted=15,
                proxies=PROXIES
            )
            
            frames = [
                df.dropna(how='all', axis=1) 
                for df in (df_remote, df_local) 
                if df is not None and not df.empty
            ]
            if not frames:
                continue
                
            jobs_df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=['job_url'])
            
            for _, row in jobs_df.iterrows():
                title = str(row.get("title", "")) if pd.notna(row.get("title")) else ""
                company = str(row.get("company", "Unknown")) if pd.notna(row.get("company")) else "Unknown"
                
                is_conservation = any(t.lower() in company.lower() for t in CONSERVATION_ENVIRONMENTAL_TARGETS)
                
                if matches_target_role(title) and is_conservation:
                    url = str(row.get("job_url", "")) if pd.notna(row.get("job_url")) else ""
                    loc = str(row.get("location", "Unspecified")) if pd.notna(row.get("location")) else "Unspecified"
                    description = str(row.get("description", "")) if pd.notna(row.get("description")) else ""
                    site = f"JobSpy ({str(row.get('site', 'Unknown'))})"
                    
                    raw_date = row.get("date_posted")
                    posted_at = str(raw_date) if pd.notna(raw_date) else None
                    
                    min_sal = row.get("min_amount")
                    if pd.notna(min_sal) and float(min_sal) > 0:
                        description += f" ${int(min_sal):,} "
                    
                    is_valid, sal_str = evaluate_salary(company, description)
                    
                    if is_valid and is_recent_enough(posted_at) and record_job(url, title, company, site, loc, sal_str, posted_at):
                        logging.info(f"[NEW] {site}: {title} -> {url}")
                        new_jobs += 1
                        
        except Exception as e:
            logging.error(f"Error executing JobSpy for term '{term}': {e}")
            
    return new_jobs

def process_custom_html_boards() -> int:
    """Requests static HTML from niche boards and parses DOM elements for job data."""
    new_jobs = 0
    targets = {
        "Conservation Job Board": "https://www.conservationjobboard.com/category/conservation-jobs",
    }
    
    for source, url in targets.items():
        try:
            response = requests.get(url, timeout=12)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                for job_card in soup.find_all('div', class_='job-listing'):
                    title_elem = job_card.find('h3')
                    if not title_elem: continue
                    title = title_elem.text.strip()
                    
                    if matches_target_role(title):
                        link_elem = job_card.find('a')
                        link = link_elem['href'] if link_elem else url
                        
                        company_elem = job_card.find('span', class_='company')
                        company = company_elem.text.strip() if company_elem else "Unknown"
                        
                        loc_elem = job_card.find('span', class_='location')
                        loc = loc_elem.text.strip() if loc_elem else "Unspecified"
                        
                        time_elem = job_card.find('time')
                        raw_date = time_elem['datetime'] if time_elem and time_elem.has_attr('datetime') else None
                        
                        is_valid, sal_str = evaluate_salary(company, "Unspecified")
                        
                        if is_valid and is_recent_enough(raw_date) and record_job(link, title, company, source, loc, sal_str, raw_date):
                            logging.info(f"[NEW] {source}: {title} -> {link}")
                            new_jobs += 1
        except Exception as e:
            logging.error(f"HTML parsing failed for {source}: {e}")
            
    return new_jobs

def process_playwright_boards() -> int:
    """Uses a local headless browser to render JavaScript-heavy enterprise boards."""
    new_jobs = 0
    
    targets = {
        "Amazon": "https://www.amazon.jobs/en/search?base_query=technical+writer",
    }
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            for source, url in targets.items():
                try:
                    page.goto(url, timeout=15000, wait_until="networkidle")
                    job_cards = page.locator('.job-tile').all()
                    
                    for card in job_cards:
                        title = card.locator('.job-title').inner_text().strip()
                        
                        if matches_target_role(title):
                            link_suffix = card.locator('a.job-link').get_attribute('href')
                            link = f"https://www.amazon.jobs{link_suffix}" if link_suffix else url
                            
                            loc_count = card.locator('.location').count()
                            loc = card.locator('.location').inner_text().strip() if loc_count > 0 else "Unspecified"
                            
                            is_valid, sal_str = evaluate_salary(source, "Unspecified")
                            
                            if is_valid and record_job(link, title, source, "Playwright", loc, sal_str, None):
                                logging.info(f"[NEW] {source}: {title} -> {link}")
                                new_jobs += 1
                                
                except Exception as e:
                    logging.error(f"Playwright failed to process {source}: {e}")
                    
            browser.close()
            
    except Exception as e:
        logging.error(f"Playwright execution failed: {e}")
        
    return new_jobs

def write_refresh_signal() -> None:
    with open(REFRESH_SIGNAL_PATH, "w", encoding="utf-8") as handle:
        handle.write(datetime.now().isoformat())

def run_aggregator(source: Optional[str] = None):
    trigger_source = source or ("Task Scheduler" if os.environ.get("TASK_SCHEDULER") else "Manual")
    logging.info(f"Starting aggregated job collection cycle via {trigger_source}...")
    init_db()
    
    total_found = (
        process_greenhouse_boards() + 
        process_ashby_boards() + 
        process_lever_boards() + 
        process_jobspy_boards() +
        process_custom_html_boards() +
        process_playwright_boards()
    )
    
    logging.info(f"Aggregation complete. Processed {total_found} new qualifying roles.")
    write_refresh_signal()

if __name__ == "__main__":
    source = None
    if len(sys.argv) > 1:
        source = sys.argv[1]
    run_aggregator(source)