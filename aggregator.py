import re
import os
import logging
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from database import init_db, record_job

# Configure Local Logging
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

LOG_FILE = os.path.join(DATA_DIR, "aggregator.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)

# Regex Match Patterns for Job Titles
TARGET_ROLE_PATTERNS = [
    r"\btechnical analyst\b", r"\btech analyst\b", r"\bbusiness analyst\b",
    r"\bsoftware analyst\b", r"\btechnical writer\b", r"\bsystems analyst\b"
]

GREENHOUSE_BOARDS = ["gitlab", "stripe", "cloudflare", "hashicorp"]
LEVER_BOARDS = ["netflix", "palantir", "spotify"]
HTML_SCRAPE_TARGETS = [{
    "company": "Example Tech",
    "url": "https://news.ycombinator.com/jobs",
    "selector": "tr.athing td.title a.titlelink"
}]

def matches_target_role(title: str) -> bool:
    for pattern in TARGET_ROLE_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE): return True
    return False

def process_greenhouse_boards() -> int:
    new_jobs_found = 0
    for board in GREENHOUSE_BOARDS:
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
        try:
            response = requests.get(api_url, timeout=12)
            if response.status_code == 200:
                for job in response.json().get("jobs", []):
                    title, job_url = job.get("title", ""), job.get("absolute_url", "")
                    loc = job.get("location", {}).get("name", "Remote")
                    if matches_target_role(title) and record_job(job_url, title, board.capitalize(), "Greenhouse", loc):
                        logging.info(f"[NEW] {title} at {board.capitalize()} -> {job_url}")
                        new_jobs_found += 1
        except Exception as e: logging.error(f"Error {board}: {e}")
    return new_jobs_found

def run_aggregator():
    logging.info("Starting aggregator run...")
    init_db()
    total = process_greenhouse_boards() # and others...
    logging.info(f"Finished. Found: {total}")

if __name__ == "__main__": run_aggregator()