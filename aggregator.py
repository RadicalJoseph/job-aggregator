# aggregator.py
import re
import os
import logging
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from database import init_db, record_job

# Configure Logging
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

LOG_FILE = os.path.join(DATA_DIR, "aggregator.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)

# ---------------------------------------------------------
# TARGET DEFINITIONS & CONFIGURATIONS
# ---------------------------------------------------------

# Title Matching Regex
TARGET_ROLE_PATTERNS = [
    r"\btechnical analyst\b", r"\btech analyst\b", r"\bbusiness analyst\b",
    r"\bsoftware analyst\b", r"\btechnical writer\b", r"\bsystems analyst\b",
    r"\batlassian administrator\b", r"\bjira administrator\b", r"\bitsm specialist\b"
]

# Standard ATS Targets
GREENHOUSE_BOARDS = {
    "atlassian": "Atlassian",
    "scaleai": "Scale AI",
    "cloverhealth": "Clover Health",
    "canonical": "Canonical",
    "github": "GitHub"
}

ASHBY_BOARDS = {
    "harvey": "Harvey",
    "firecrawl": "Firecrawl"
}

LEVER_BOARDS = {
    "netflix": "Netflix"
}

# Environmental, Conservation, and Nonprofit Targets (Minimum $80,000 Salary Required)
CONSERVATION_ENVIRONMENTAL_TARGETS = [
    "Climatebase",
    "Conservation International (CI)",
    "Conservation Job Board",
    "Environmental Defense Fund (EDF)",
    "Green Jobs Network",
    "Land Trust Alliance Job Board",
    "Maine Coast Heritage Trust (MCHT)",
    "National Audubon Society",
    "Natural Resources Council (NRC)",
    "Natural Resources Defense Council (NRDC)",
    "Society for Conservation Biology Job Board",
    "The Conservation Fund",
    "Wildlife Conservation Society (WCS)",
    "World Resources Institute (WRI)",
    "World Wildlife Fund (WWF)",
    "Idealist"
]

# Additional High-Volume Job Boards & Portals (Custom Scrapers / API endpoints)
GENERAL_JOB_BOARDS = [
    "Amazon", "Apple", "Built In", "Dice", "Glassdoor", "Google", "Google Jobs",
    "Himalayas", "Hiring Cafe", "Indeed", "LinkedIn", "Meta", "Microsoft", 
    "Otta", "SimplyHired", "Welcome to the Jungle", "Wellfound", "WriteFolks", "ZipRecruiter"
]

MIN_CONSERVATION_SALARY = 80000

# ---------------------------------------------------------
# HELPER & VALIDATION FUNCTIONS
# ---------------------------------------------------------

def matches_target_role(title: str) -> bool:
    """Check if the job title matches specified regex patterns."""
    for pattern in TARGET_ROLE_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            return True
    return False

def parse_salary_floor(text: str) -> Optional[int]:
    """
    Extracts numerical salary minimums from text strings (e.g., "$85,000 - $110,000" or "80k").
    Returns the lower bounds integer value if found.
    """
    if not text:
        return None
    
    # Match patterns like $80,000, $80k, 80,000 USD
    k_matches = re.findall(r'\$?\s*(\d{2,3})\s*k\b', text, re.IGNORECASE)
    if k_matches:
        return int(k_matches[0]) * 1000

    full_num_matches = re.findall(r'\$\s*(\d{2,3},\d{3})', text)
    if full_num_matches:
        return int(full_num_matches[0].replace(",", ""))

    return None

def validates_salary_requirement(company_or_source: str, salary_text: str) -> bool:
    """
    Enforces minimum $80,000 USD salary requirement specifically for
    Environmental, Conservation, and Non-Profit targets.
    """
    is_conservation = any(
        target.lower() in company_or_source.lower() 
        for target in CONSERVATION_ENVIRONMENTAL_TARGETS
    )

    if not is_conservation:
        return True  # Non-conservation jobs pass without salary enforcement

    salary_floor = parse_salary_floor(salary_text)
    
    # If salary info is explicitly provided, validate threshold; if unlisted, log for manual review
    if salary_floor is not None:
        return salary_floor >= MIN_CONSERVATION_SALARY
    
    return True

# ---------------------------------------------------------
# ATS PIPELINE INGESTION LOGIC
# ---------------------------------------------------------

def process_greenhouse_boards() -> int:
    """Query standard Greenhouse API endpoints."""
    new_jobs = 0
    for board_token, display_name in GREENHOUSE_BOARDS.items():
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
        try:
            res = requests.get(api_url, timeout=12)
            if res.status_code == 200:
                for job in res.json().get("jobs", []):
                    title = job.get("title", "")
                    url = job.get("absolute_url", "")
                    location = job.get("location", {}).get("name", "Remote")
                    content = job.get("content", "")

                    if matches_target_role(title):
                        if validates_salary_requirement(display_name, content):
                            if record_job(url, title, display_name, "Greenhouse API", location):
                                logging.info(f"[NEW] {display_name}: {title} -> {url}")
                                new_jobs += 1
        except Exception as e:
            logging.error(f"Error querying Greenhouse board {display_name}: {e}")
    return new_jobs

def process_ashby_boards() -> int:
    """Query Ashby API endpoints via public posting routes."""
    new_jobs = 0
    for board_token, display_name in ASHBY_BOARDS.items():
        api_url = f"https://api.ashbyhq.com/posting-api/job-board/{board_token}"
        try:
            res = requests.get(api_url, timeout=12)
            if res.status_code == 200:
                jobs = res.json().get("jobs", [])
                for job in jobs:
                    title = job.get("title", "")
                    url = job.get("jobUrl", "")
                    location = job.get("locationName", "Remote")
                    
                    if matches_target_role(title):
                        if validates_salary_requirement(display_name, str(job)):
                            if record_job(url, title, display_name, "Ashby API", location):
                                logging.info(f"[NEW] {display_name}: {title} -> {url}")
                                new_jobs += 1
        except Exception as e:
            logging.error(f"Error querying Ashby board {display_name}: {e}")
    return new_jobs

def process_lever_boards() -> int:
    """Query Lever REST API endpoints."""
    new_jobs = 0
    for board_token, display_name in LEVER_BOARDS.items():
        api_url = f"https://api.lever.co/v0/postings/{board_token}?mode=json"
        try:
            res = requests.get(api_url, timeout=12)
            if res.status_code == 200:
                for job in res.json():
                    title = job.get("text", "")
                    url = job.get("hostedUrl", "")
                    categories = job.get("categories", {})
                    location = categories.get("location", "Remote")
                    description = job.get("descriptionPlain", "")

                    if matches_target_role(title):
                        if validates_salary_requirement(display_name, description):
                            if record_job(url, title, display_name, "Lever API", location):
                                logging.info(f"[NEW] {display_name}: {title} -> {url}")
                                new_jobs += 1
        except Exception as e:
            logging.error(f"Error querying Lever board {display_name}: {e}")
    return new_jobs

def process_custom_enterprise_apis() -> int:
    """
    Placeholder endpoint handler for direct corporate search endpoints:
    Amazon (amazon.jobs), Microsoft (gcsservices.careers.microsoft.com), Apple, Meta, Google.
    """
    new_jobs = 0
    # Custom payload query structures for direct search endpoints can be registered here.
    return new_jobs

# ---------------------------------------------------------
# AGGREGATOR EXECUTION ENTRY POINT
# ---------------------------------------------------------

def run_aggregator():
    logging.info("Starting aggregated job collection cycle...")
    init_db()
    
    total_found = 0
    total_found += process_greenhouse_boards()
    total_found += process_ashby_boards()
    total_found += process_lever_boards()
    total_found += process_custom_enterprise_apis()

    logging.info(f"Aggregation complete. Processed {total_found} new qualifying roles.")

if __name__ == "__main__":
    run_aggregator()