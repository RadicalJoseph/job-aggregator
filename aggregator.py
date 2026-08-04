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

# --- Module: Open ATS Integrations ---
def fetch_greenhouse_lever_ashby() -> set:
    seen_urls = set()
    # Expanded list of target tech companies using open ATS endpoints
    companies = ["atlassian", "scaleai", "cloverhealth", "harvey", "firecrawl", "canonical", "github"]
    
    for company in companies:
        # Example using Greenhouse API format
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"
        try:
            res = requests.get(api_url, timeout=10)
            if res.status_code == 200:
                for job in res.json().get("jobs", []):
                    title = job.get("title", "")
                    url = job.get("absolute_url", "")
                    loc = job.get("location", {}).get("name", "")
                    salary_text = job.get("content", "")
                    
                    if evaluate_job(title, company, loc, salary_text):
                        seen_urls.add(url)
                        if upsert_job(url, title, company, "Direct ATS", loc, "Parsed"):
                            logging.info(f"[NEW] {title} at {company} -> {url}")
        except Exception as e:
            pass # Suppress API misses for non-Greenhouse domains in this loop
    return seen_urls

# --- Module: Walled-Garden Boards via Apify ---
def fetch_protected_boards() -> set:
    if not APIFY_TOKEN:
        logging.warning("No Apify token set. Skipping Indeed, LinkedIn, Dice, Hiring Cafe.")
        return set()
    
    client = ApifyClient(APIFY_TOKEN)
    seen_urls = set()
    
    # 1. Hiring Cafe Actor
    hc_input = {
        "keyword": "Atlassian OR AI Enablement OR Technical Writer OR Business Analyst",
        "location": "United States",
        "workplaceType": "Any",
        "dateFetchedPastNDays": 1 
    }
    hc_run = client.actor("memo23/apify-hiring-cafe-scraper").call(run_input=hc_input)
    for item in client.dataset(hc_run["defaultDatasetId"]).iterate_items():
        title = item.get("title", "")
        company = item.get("company", "")
        url = item.get("applyLink", "")
        loc = item.get("location", "")
        sal = str(item.get("salary", ""))
        
        if evaluate_job(title, company, loc, sal):
            seen_urls.add(url)
            if upsert_job(url, title, company, "Hiring Cafe", loc, sal):
                logging.info(f"[NEW HC] {title} at {company} -> {url}")

    # 2. Built In Actor
    bi_input = {"proxyConfiguration": {"useApifyProxy": True, "apifyProxyCountry": "US"}}
    bi_run = client.actor("jobsapi/builtin-jobs-search-scraper").call(run_input=bi_input)
    for item in client.dataset(bi_run["defaultDatasetId"]).iterate_items():
        title = item.get("title", "")
        company = item.get("company", "")
        url = item.get("url", "")
        loc = item.get("location", "")
        sal = item.get("salaryRange", "")
        
        if evaluate_job(title, company, loc, sal):
            seen_urls.add(url)
            if upsert_job(url, title, company, "Built In", loc, sal):
                logging.info(f"[NEW BUILTIN] {title} at {company} -> {url}")
                
    # NOTE: Add additional Apify actor calls here for Dice (jobsapi/dice-com-jobs-search-scraper), 
    # LinkedIn, and Indeed following the identical dataset iteration pattern above.
    
    return seen_urls

def execute_pipeline():
    init_db()
    logging.info("Starting comprehensive job board aggregation...")
    
    ats_urls = fetch_greenhouse_lever_ashby()
    protected_urls = fetch_protected_boards()
    
    all_active_urls = ats_urls.union(protected_urls)
    
    # Reconcile for the 2-week lookback
    removed = reconcile_missing_jobs(all_active_urls, "Direct ATS", 14)
    removed += reconcile_missing_jobs(all_active_urls, "Hiring Cafe", 14)
    removed += reconcile_missing_jobs(all_active_urls, "Built In", 14)
    
    for r in removed:
        logging.info(f"[STATUS CHANGE] Role taken down or filled: {r}")

if __name__ == "__main__":
    execute_pipeline()