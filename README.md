# Local Job Board Aggregator

A Python-based automation engine and desktop management interface designed to aggregate career postings from multi-ATS endpoints (Greenhouse, Ashby, Lever), enforce automated salary filters, and manage application workflows locally.

---

## Architecture Overview

The aggregator runs locally as a background process, deduplicating target postings into a local SQLite database and generating structured logs. A lightweight Tkinter graphical user interface (GUI) provides real-time state tracking and application management without external web service dependencies.

```text
job-board-aggregator/
├── .gitignore
├── README.md
├── requirements.txt
├── database.py
├── aggregator.py
├── viewer.py
└── data/             <-- Created at runtime (ignored by Git)
    ├── jobs.db
    └── aggregator.log

Key Features

    Multi-ATS Integration: REST API query handlers for Greenhouse, Ashby, and Lever boards.

    Automated Filtering & Salary Validation: Regex matching for target technical roles combined with automatic salary floor validation ($80,000 USD minimum for targeted non-profit and environmental roles).

    Local Persistence: Zero-external-dependency SQLite database ensuring job postings are stored permanently and processed only once.

    Interactive Desktop GUI: Built-in Tkinter viewer featuring dual-tab views for database records and execution logs, double-click URL copying, and interactive status tracking (Applied, Ignored, Rejected).

    Background Scheduling: Native compatibility with Windows Task Scheduler and Unix cron.

Environment Setup & Installation
Prerequisites

    Python 3.10+ (with standard tcl/tk support enabled)

    Git

Installation Steps

    Clone the Repository:
    Bash

    git clone [https://github.com/your-username/job-board-aggregator.git](https://github.com/your-username/job-board-aggregator.git)
    cd job-board-aggregator

    Establish Virtual Environment:

        macOS/Linux:
        Bash

        python3 -m venv venv
        source venv/bin/activate

        Windows (PowerShell):
        PowerShell

        py -3.11 -m venv venv
        .\venv\Scripts\Activate.ps1

    Install Dependencies:
    Bash

    pip install --upgrade pip
    pip install -r requirements.txt
    python -m playwright install chromium

Module Overview

    database.py: Manages the SQLite database (data/jobs.db), defining table schemas for job postings, salary parsing results, discovery timestamps, and application statuses.

    aggregator.py: Execution engine that queries target job board endpoints, evaluates regex title matches, enforces salary criteria, and writes new roles to the database.

    viewer.py: Desktop GUI for managing records, copying application URLs, and tracking application progress.

Automation Setup
Windows Task Scheduler

To configure the aggregator to execute every 4 hours automatically in the background, run the following script in an elevated PowerShell session:
PowerShell

# Define execution properties (update paths to match your local installation)
$Action = New-ScheduledTaskAction -Execute "C:\path\to\job-board-aggregator\venv\Scripts\python.exe" -Argument "C:\path\to\job-board-aggregator\aggregator.py"

# Establish 4-hour interval trigger
$Trigger = New-ScheduledTaskTrigger -Once -At 8:00AM -RepetitionInterval (New-TimeSpan -Hours 4)

# Register task
Register-ScheduledTask -TaskName "LocalJobBoardAggregator" -Action $Action -Trigger$Trigger

macOS / Linux (cron)

Add an entry to your crontab (crontab -e) to execute the aggregator every 4 hours:
Bash

0 */4 * * * /path/to/job-board-aggregator/venv/bin/python /path/to/job-board-aggregator/aggregator.py >> /path/to/job-board-aggregator/data/cron.log 2>&1

Operational Guide

    Launch the Interface:
    PowerShell

    python viewer.py

    Review Listings:

        Copy URL: Double-click any row in the Database Records tab to copy the job application link to your clipboard.

        Toggle Status: Single-click a checkbox column (Applied, Ignored, or Rejected) to set or toggle the role's status.

    Manual Pipeline Execution:
    To force an immediate aggregation run outside of scheduled triggers:
    PowerShell

    python aggregator.py