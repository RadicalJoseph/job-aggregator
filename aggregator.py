# aggregator.py
import re
import logging
import pandas as pd
import requests
from jobspy import scrape_jobs
from database import init_db, upsert_job, reconcile_missing_jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Configuration & Filters ---
TARGET_LEVELS = [r"\bsenior\b", r"\blead\b", r"\bmanager\b", r"\bdirector\b", r"\bsr\b"]
TARGET_DOMAINS = [
    r"\btechnical writ", r"\bdocumentation\b", r"\bai enablement\b", r"\bai\b", 
    r"\batlassian\b", r"\bjira\b", r"\bconfluence\b", 
    r"\btechnical analyst\b", r"\btech analyst\b", r"\bbusiness analyst\b", r"\bsoftware analyst\b"
]
EXCLUDED_COMPANIES = ["syllo", "coupa", "campminder", "capital one"]
TARGET_LOCATIONS = ["remote", "maine", "me", "portland"]

def evaluate_job(title: str, company: str, location: str, min_salary: float, max_salary: float) -> bool:
    """Evaluates job against all user constraints."""
    if not company or any(ex in str(company).lower() for ex in EXCLUDED_COMPANIES):
        return False

    title_lower = str(title).lower()
    loc_lower = str(location).lower()

    # Check Seniority & Domain
    has_level = any(re.search(level, title_lower) for level in TARGET_LEVELS)
    has_domain = any(re.search(domain, title_lower) for domain in TARGET_DOMAINS)
    if not (has_level and has_domain):
        return False

    # Check Location (Remote, Maine, or Portland)
    if not any(loc in loc_lower for loc in TARGET_LOCATIONS):
        return False

    # Check Salary Threshold ($110,000+)
    highest_sal = max(min_salary or 0, max_salary or 0)
    if highest_sal > 0 and highest_sal < 110000:
        return False

    return True

# --- Module 1: JobSpy Aggregator (LinkedIn, Indeed, Google) ---
def fetch_jobspy_boards() -> set:
    seen_urls = set()
    logging.info("Starting JobSpy scrape (Indeed, LinkedIn, Google)...")
    
    try:
        # JobSpy scrapes all requested boards concurrently
        jobs_df = scrape_jobs(
            site_name=["indeed", "linkedin", "google"], # Glassdoor and ZipRecruiter can also be added here
            search_term="Technical Writer OR AI Enablement OR Atlassian OR Business Analyst",
            location="United States",
            results_wanted=50,
            hours_old=24, # Filters for roles posted in the last 24 hours
            country_indeed='USA'
        )
        
        for _, row in jobs_df.iterrows():
            title = row.get("title")
            company = row.get("company")
            url = row.get("job_url")
            loc = f"{row.get('city', '')}, {row.get('state', '')}"
            min_sal = row.get("min_amount") if pd.notna(row.get("min_amount")) else 0
            max_sal = row.get("max_amount") if pd.notna(row.get("max_amount")) else 0
            
            if evaluate_job(title, company, loc, min_sal, max_sal):
                seen_urls.add(url)
                sal_str = f"${min_sal}-${max_sal}" if min_sal else "Unlisted"
                source = row.get("site")
                
                if upsert_job(url, title, company, f"JobSpy ({source})", loc, sal_str):
                    logging.info(f"[NEW {source.upper()}] {title} at {company} -> {url}")
                    
    except Exception as e:
        logging.error(f"JobSpy scraping error: {e}")
        
    return seen_urls

# --- Module 2: Open ATS Integrations (Greenhouse, Lever, Ashby) ---
def fetch_ats_boards() -> set:
    seen_urls = set()
    companies = ["atlassian", "scaleai", "cloverhealth", "canonical", "github", "harvey", "firecrawl"]
    
    for board in companies:
        try:
            # Simple fallback regex parser for ATS descriptions if they don't provide clean JSON salary data
            url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                for job in res.json().get("jobs", []):
                    title = job.get("title", "")
                    job_url = job.get("absolute_url", "")
                    loc = job.get("location", {}).get("name", "")
                    content = job.get("content", "")
                    
                    # Extract salary numbers to pass to evaluate_job
                    salary_nums = [int(n.replace(',', '')) for n in re.findall(r'\b\d{3,4}(?:,\d{3})\b', content)]
                    max_sal = max(salary_nums) if salary_nums else 0
                    
                    if evaluate_job(title, board, loc, 0, max_sal):
                        seen_urls.add(job_url)
                        upsert_job(job_url, title, board.capitalize(), "Direct ATS", loc, "Parsed from Text")
        except Exception:
            pass 
            
    return seen_urls

def execute_pipeline():
    init_db()
    logging.info("Starting Open-Source Job Aggregation...")
    
    jobspy_urls = fetch_jobspy_boards()
    ats_urls = fetch_ats_boards()
    
    all_active_urls = jobspy_urls.union(ats_urls)
    
    # Reconcile for the 2-week lookback
    sources = ["JobSpy (linkedin)", "JobSpy (indeed)", "JobSpy (google)", "Direct ATS"]
    for source in sources:
        removed = reconcile_missing_jobs(all_active_urls, source, 14)
        for r in removed:
            logging.info(f"[STATUS CHANGE] Role taken down or filled: {r}")

if __name__ == "__main__":
    execute_pipeline()