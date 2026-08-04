# aggregator.py
import re
import logging
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Tuple
from playwright.sync_api import sync_playwright
from database import init_db, upsert_job, reconcile_missing_jobs

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Filtering Regexes
ROLE_PATTERNS = [
    r"\btechnical analyst\b", r"\btech analyst\b", r"\bbusiness analyst\b",
    r"\bsoftware analyst\b", r"\btechnical writer\b", r"\bai enablement\b",
    r"\batlassian\b", r"\bjira\b", r"\bconfluence\b"
]

LOCATION_PATTERNS = [r"\bremote\b", r"\bmaine\b", r"\bportland\b"]
EXCLUDED_COMPANIES = ["syllo", "coupa", "campminder", "capital one"]

def matches_filters(title: str, location: str, company: str) -> bool:
    if any(ex.lower() in company.lower() for ex in EXCLUDED_COMPANIES):
        return False
    
    title_match = any(re.search(pat, title, re.IGNORECASE) for pat in ROLE_PATTERNS)
    loc_match = any(re.search(pat, location, re.IGNORECASE) for pat in LOCATION_PATTERNS) if location else True
    
    return title_match and loc_match

def parse_salary(text: str) -> str:
    """Extract dollar figures or ranges from text blocks."""
    match = re.search(r"\$\d{2,3}(?:,\d{3})*(?:\s*-\s*\$\d{2,3}(?:,\d{3})*)?", text)
    return match.group(0) if match else "Unlisted"

# --- Source 1: Greenhouse API ---
def fetch_greenhouse(boards: List[str]) -> set:
    seen_urls = set()
    for board in boards:
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
        try:
            res = requests.get(api_url, timeout=10)
            if res.status_code == 200:
                for job in res.json().get("jobs", []):
                    title = job.get("title", "")
                    url = job.get("absolute_url", "")
                    loc = job.get("location", {}).get("name", "Remote")
                    content = job.get("content", "")
                    salary = parse_salary(content)
                    
                    if matches_filters(title, loc, board):
                        seen_urls.add(url)
                        is_new = upsert_job(url, title, board.capitalize(), "Greenhouse", loc, salary)
                        if is_new:
                            logging.info(f"[NEW GREENHOUSE] {title} at {board.capitalize()} ({salary}) -> {url}")
        except Exception as e:
            logging.error(f"Greenhouse error for {board}: {e}")
    return seen_urls

# --- Source 2: Ashby API ---
def fetch_ashby(companies: List[str]) -> set:
    seen_urls = set()
    for company in companies:
        api_url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
        try:
            res = requests.get(api_url, timeout=10)
            if res.status_code == 200:
                for job in res.json().get("jobs", []):
                    title = job.get("title", "")
                    url = job.get("jobUrl", "")
                    loc = job.get("location", "Remote")
                    salary = parse_salary(str(job.get("compensation", "")))
                    
                    if matches_filters(title, loc, company):
                        seen_urls.add(url)
                        is_new = upsert_job(url, title, company.capitalize(), "Ashby", loc, salary)
                        if is_new:
                            logging.info(f"[NEW ASHBY] {title} at {company.capitalize()} ({salary}) -> {url}")
        except Exception as e:
            logging.error(f"Ashby error for {company}: {e}")
    return seen_urls

# --- Source 3: Dynamic Browser Scraper (Playwright) for Headless Boards ---
def fetch_rendered_board(target_url: str, source_name: str, selector: str) -> set:
    seen_urls = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")
        page = context.new_page()
        try:
            page.goto(target_url, wait_until="networkidle", timeout=30000)
            elements = page.query_selector_all(selector)
            
            for el in elements:
                title = el.inner_text().strip()
                href = el.get_attribute("href")
                url = href if href.startswith("http") else f"{target_url.rstrip('/')}/{href.lstrip('/')}"
                
                if matches_filters(title, "Remote", source_name):
                    seen_urls.add(url)
                    is_new = upsert_job(url, title, source_name, source_name, "Remote/Unspecified", "Unlisted")
                    if is_new:
                        logging.info(f"[NEW PLAYWRIGHT] {title} at {source_name} -> {url}")
        except Exception as e:
            logging.error(f"Playwright error on {target_url}: {e}")
        finally:
            browser.close()
    return seen_urls

def run_aggregator():
    init_db()
    
    # 1. Greenhouse Targets
    gh_boards = ["gitlab", "stripe", "cloudflare", "hashicorp", "starburst", "iterable", "cloverhealth"]
    gh_seen = fetch_greenhouse(gh_boards)
    gh_removed = reconcile_missing_jobs(gh_seen, "Greenhouse")
    
    # 2. Ashby Targets
    ashby_boards = ["harvey", "firecrawl"]
    ashby_seen = fetch_ashby(ashby_boards)
    ashby_removed = reconcile_missing_jobs(ashby_seen, "Ashby")
    
    # 3. Custom Dynamic Targets via Playwright
    # (Used for sites rendering job lists via JS without public APIs)
    builtin_seen = fetch_rendered_board("https://builtin.com/jobs/remote/tech", "BuiltIn", "a.job-title")
    
    # Report closed roles
    all_removed = gh_removed + ashby_removed
    for removed_job in all_removed:
        logging.info(f"[CLOSED/REMOVED] {removed_job['title']} at {removed_job['company']} -> {removed_job['url']}")

if __name__ == "__main__":
    run_aggregator()