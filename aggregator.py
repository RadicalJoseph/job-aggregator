# aggregator.py
import re
import os
import logging
import requests
from typing import Optional, Tuple
from database import init_db, record_job

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

LOG_FILE = os.path.join(DATA_DIR, "aggregator.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)

TARGET_ROLE_PATTERNS = [
    r"\btechnical analyst\b", r"\btech analyst\b", r"\bbusiness analyst\b",
    r"\bsoftware analyst\b", r"\btechnical writer\b", r"\bsystems analyst\b",
    r"\batlassian administrator\b", r"\bjira administrator\b", r"\bitsm specialist\b"
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
                        if is_valid and record_job(url, title, display_name, "Greenhouse API", loc, sal_str):
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
                        if is_valid and record_job(url, title, display_name, "Ashby API", loc, sal_str):
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
                        if is_valid and record_job(url, title, display_name, "Lever API", loc, sal_str):
                            logging.info(f"[NEW] {display_name}: {title} -> {url}")
                            new_jobs += 1
        except Exception as e: logging.error(f"Error {display_name}: {e}")
    return new_jobs

def run_aggregator():
    logging.info("Starting aggregated job collection cycle...")
    init_db()
    total_found = process_greenhouse_boards() + process_ashby_boards() + process_lever_boards()
    logging.info(f"Aggregation complete. Processed {total_found} new qualifying roles.")

if __name__ == "__main__":
    run_aggregator()