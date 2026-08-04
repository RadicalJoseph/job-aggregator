# aggregator.py
import re
import os
import logging
import requests
from datetime import datetime, timedelta
from apify_client import ApifyClient
from database import init_db, upsert_job, reconcile_missing_jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Configuration & Filters ---
APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")
TARGET_LEVELS = [r"\bsenior\b", r"\blead\b", r"\bmanager\b", r"\bdirector\b", r"\bsr\b"]
TARGET_DOMAINS = [
    r"\btechnical writ", r"\bdocumentation\b", r"\bai enablement\b", r"\bai\b", 
    r"\batlassian\b", r"\bjira\b", r"\bconfluence\b", 
    r"\btechnical analyst\b", r"\btech analyst\b", r"\bbusiness analyst\b", r"\bsoftware analyst\b"
]
EXCLUDED_COMPANIES = ["syllo", "coupa", "campminder", "capital one"]
TARGET_LOCATIONS = ["remote", "maine", "me", "portland"]

def evaluate_job(title: str, company: str, location: str, salary_text: str) -> bool:
    """Evaluates job against all user constraints."""
    if any(ex in company.lower() for ex in EXCLUDED_COMPANIES):
        return False

    title_lower = title.lower()
    loc_lower = location.lower() if location else ""

    # Check Seniority & Domain
    has_level = any(re.search(level, title_lower) for level in TARGET_LEVELS)
    has_domain = any(re.search(domain, title_lower) for domain in TARGET_DOMAINS)
    if not (has_level and has_domain):
        return False

    # Check Location (Remote, Maine, or Portland)
    if not any(loc in loc_lower for loc in TARGET_LOCATIONS):
        return False

    # Check Salary Threshold ($110,000+)
    salary_nums = [int(n.replace(',', '')) for n in re.findall(r'\b\d{3,4}(?:,\d{3})\b', salary_text)]
    if salary_nums:
        max_val = max(salary_nums)
        if max_val < 110000:
            return False

    return True

# --- Module 1: FAANG/MANGOS Direct APIs ---
def fetch_faang_apis() -> set:
    """Direct queries to public endpoints for Big Tech."""
    seen_urls = set()
    
    # 1. Amazon Jobs (via documented json search API format)
    # Amazon uses amazon.jobs for its careers site.
    # It allows searches by keyword and category, returning structured JSON.
    try:
        amz_url = "https://www.amazon.jobs/en/search.json?base_query=technical+writer&sort=recent"
        amz_res = requests.get(amz_url, timeout=10)
        if amz_res.status_code == 200:
            for job in amz_res.json().get("jobs", []):
                title = job.get("title", "")
                loc = job.get("city", "")
                url = f"https://www.amazon.jobs/en/jobs/{job.get('id_icims')}"
                if evaluate_job(title, "Amazon", loc, ""):
                    seen_urls.add(url)
                    upsert_job(url, title, "Amazon", "Amazon API", loc, "Unlisted")
    except Exception as e:
        logging.error(f"Amazon API error: {e}")

    # 2. Netflix, Meta, Google, Apple (Stubbed for API format)
    # Note: Netflix uses jobs.netflix.com, but complex search requires specific graphQL/REST payloads.
    # Microsoft uses gcsservices.careers.microsoft.com, which requires dual bearer tokens.
    # In a fully headless environment, Microsoft and Google are best routed through Apify.
    
    return seen_urls

# --- Module 2: Open ATS Integrations (Greenhouse, Lever, Ashby) ---
def fetch_ats_boards() -> set:
    """Queries standard REST endpoints for mid-tier tech companies."""
    seen_urls = set()
    # List of known target companies using these systems
    gh_boards = ["atlassian", "scaleai", "cloverhealth", "canonical", "github"]
    ashby_boards = ["harvey", "firecrawl"]
    
    for board in gh_boards:
        try:
            url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                for job in res.json().get("jobs", []):
                    title = job.get("title", "")
                    job_url = job.get("absolute_url", "")
                    loc = job.get("location", {}).get("name", "")
                    salary = job.get("content", "")
                    if evaluate_job(title, board, loc, salary):
                        seen_urls.add(job_url)
                        upsert_job(job_url, title, board.capitalize(), "Greenhouse", loc, "Parsed")
        except Exception:
            pass 
            
    # Add identical loop block for Ashby boards here...
    return seen_urls

# --- Module 3: Walled-Garden Boards via Apify ---
def fetch_protected_boards() -> set:
    """Routes heavily protected aggregators through Apify Actors."""
    if not APIFY_TOKEN:
        logging.warning("No Apify token set. Skipping protected boards.")
        return set()
    
    client = ApifyClient(APIFY_TOKEN)
    seen_urls = set()
    
    # 1. LinkedIn (via bebity/linkedin-jobs-scraper)
    # The LinkedIn Jobs Scraper is called via its ID: bebity/linkedin-jobs-scraper.
    li_input = {
        "title": "Technical Writer OR Business Analyst OR AI Enablement",
        "location": "United States",
        "contractType": ["F"], 
        "datePosted": "r86400" # Past 24 hours 
    }
    li_run = client.actor("bebity/linkedin-jobs-scraper").call(run_input=li_input)
    for item in client.dataset(li_run["defaultDatasetId"]).iterate_items():
        title = item.get("title", "")
        company = item.get("companyName", "")
        url = item.get("url", "")
        loc = item.get("location", "")
        if evaluate_job(title, company, loc, ""):
            seen_urls.add(url)
            upsert_job(url, title, company, "LinkedIn", loc, "Unlisted")

    # 2. Hiring Cafe
    hc_run = client.actor("memo23/apify-hiring-cafe-scraper").call(
        run_input={"keyword": "Atlassian", "dateFetchedPastNDays": 1}
    )
    for item in client.dataset(hc_run["defaultDatasetId"]).iterate_items():
        title = item.get("title", "")
        company = item.get("company", "")
        url = item.get("applyLink", "")
        sal = str(item.get("salary", ""))
        if evaluate_job(title, company, item.get("location", ""), sal):
            seen_urls.add(url)
            upsert_job(url, title, company, "Hiring Cafe", item.get("location", ""), sal)

    # 3. Built In
    bi_run = client.actor("jobsapi/builtin-jobs-search-scraper").call(
        run_input={"proxyConfiguration": {"useApifyProxy": True, "apifyProxyCountry": "US"}}
    )
    for item in client.dataset(bi_run["defaultDatasetId"]).iterate_items():
        title = item.get("title", "")
        company = item.get("company", "")
        url = item.get("url", "")
        sal = item.get("salaryRange", "")
        if evaluate_job(title, company, item.get("location", ""), sal):
            seen_urls.add(url)
            upsert_job(url, title, company, "Built In", item.get("location", ""), sal)

    # NOTE: The implementation block for Indeed, Dice, Otta, Wellfound, Welcome to the Jungle, and WriteFolks 
    # follows the exact same iterative Apify Actor structure as above.

    return seen_urls

def execute_pipeline():
    init_db()
    logging.info("Starting comprehensive job board aggregation...")
    
    # Execute all modules
    faang_urls = fetch_faang_apis()
    ats_urls = fetch_ats_boards()
    protected_urls = fetch_protected_boards()
    
    # Combine all discovered URLs
    all_active_urls = faang_urls.union(ats_urls).union(protected_urls)
    
    # Reconcile for the 2-week lookback
    sources = ["Amazon API", "Greenhouse", "LinkedIn", "Hiring Cafe", "Built In"]
    for source in sources:
        removed = reconcile_missing_jobs(all_active_urls, source, 14)
        for r in removed:
            logging.info(f"[STATUS CHANGE] Role taken down or filled: {r}")

if __name__ == "__main__":
    execute_pipeline()