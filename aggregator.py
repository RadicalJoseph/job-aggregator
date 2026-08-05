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
    "canonical": "Canonical", "github": "GitHub"
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
    """Parses salary and determines if it meets organizational requirements."""
    floor = parse_salary_floor(text)
    salary_str = f"${floor:,}" if floor else "Unspecified"

    is_conservation = any(t.lower() in company_or_source.lower() for t in CONSERVATION_ENVIRONMENTAL_TARGETS)

    if is_conservation and floor is not None:
        return (floor >= MIN_CONSERVATION_SALARY, salary_str)
    return (True, salary_str)


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
                        if is_valid and record_job(url, title, company_name, "Greenhouse API", loc, sal_str, posted_at):
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
                        if is_valid and record_job(url, title, company_name, "Ashby API", loc, sal_str, posted_at):
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
                        if is_valid and record_job(url, title, company_name, "Lever API", loc, sal_str, posted_at):
                            logging.info(f"[NEW] {display_name}: {title} -> {url}")
                            new_jobs += 1
        except Exception as e: logging.error(f"Error {display_name}: {e}")
    return new_jobs

def process_jobspy_boards() -> int:
    """
    Executes concurrent scraping across primary job boards using jobspy.
    Filters the pandas DataFrame output against existing target roles and records matches.
    """
    new_jobs = 0
    
    # Define broad search terms that align with the established TARGET_ROLE_PATTERNS
    search_terms = ["Atlassian Administrator", "Technical Writer", "Knowledge Management", "Systems Analyst"]
    
    for term in search_terms:
        try:
            # Scrape up to 30 recent remote roles per search term across major boards
            jobs_df = scrape_jobs(
                site_name=["linkedin", "indeed", "glassdoor"],
                search_term=term,
                location="Remote",
                results_wanted=30
            )
            
            # Skip processing if the dataframe is empty or invalid
            if jobs_df is None or jobs_df.empty:
                continue
                
            # Iterate through the returned dataframe rows
            for _, row in jobs_df.iterrows():
                title = str(row.get("title", ""))
                
                # Utilize the existing regex matching logic from aggregator.py
                if matches_target_role(title):
                    url = str(row.get("job_url", ""))
                    company = str(row.get("company", "Unknown"))
                    loc = str(row.get("location", "Remote"))
                    description = str(row.get("description", ""))
                    posted_at = str(row.get("date_posted", ""))
                    site = f"JobSpy ({str(row.get('site', 'Unknown'))})"
                    
                    # Evaluate salary requirements and conservation status[cite: 2]
                    is_valid, sal_str = evaluate_salary(company, description)
                    
                    # Record the job if it passes validation and does not already exist[cite: 4]
                    if is_valid and record_job(url, title, company, site, loc, sal_str, posted_at):
                        logging.info(f"[NEW] {site}: {title} -> {url}")
                        new_jobs += 1
                        
        except Exception as e:
            logging.error(f"Error executing JobSpy for term '{term}': {e}")
            
    return new_jobs

def write_refresh_signal() -> None:
    with open(REFRESH_SIGNAL_PATH, "w", encoding="utf-8") as handle:
        handle.write(datetime.now().isoformat())


def run_aggregator(source: Optional[str] = None):
    trigger_source = source or ("Task Scheduler" if os.environ.get("TASK_SCHEDULER") else "Manual")
    logging.info(f"Starting aggregated job collection cycle via {trigger_source}...")
    init_db()
    total_found = process_greenhouse_boards() + process_ashby_boards() + process_lever_boards() + process_jobspy_boards()
    logging.info(f"Aggregation complete. Processed {total_found} new qualifying roles.")
    write_refresh_signal()

if __name__ == "__main__":
    source = None
    if len(sys.argv) > 1:
        source = sys.argv[1]
    run_aggregator(source)