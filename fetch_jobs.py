#!/usr/bin/env python3
"""
AWS Data Engineer Job Bot (India)
----------------------------------
Fetches recent job postings from Adzuna (India), scores them against your
skillset, and pushes high-match new listings to you via Telegram.

Designed to run on a schedule (GitHub Actions cron). Fully pause-able via
a `pause.flag` file in the repo root -- if that file exists, the script
exits immediately without fetching or notifying anything.

No auto-apply is performed. This tool finds and ranks jobs and sends you
a one-tap link; you make the final call and click Apply yourself. This
keeps you off the radar of anti-bot systems on job portals and avoids
submitting generic/spammy applications that hurt your shortlist odds.
"""

import os
import sys
import json
import time
import requests

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------

ADZUNA_APP_ID = os.environ.get("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

SEEN_JOBS_FILE = "seen_jobs.json"
PAUSE_FILE = "pause.flag"

# Search queries to cast a wide-but-relevant net across how these roles
# actually get titled in India.
SEARCH_QUERIES = [
    "AWS Data Engineer",
    "Data Engineer AWS Glue",
    "PySpark Data Engineer",
    "Databricks Data Engineer",
    "Big Data Engineer AWS",
    "Data Engineer Airflow",
    "Cloud Data Engineer AWS",
]

# Your skillset -- used to score each JD for relevance.
MY_SKILLS = [
    "aws", "glue", "s3", "athena", "mwaa", "airflow", "iam",
    "step function", "step functions", "kms", "vpc", "ec2",
    "secret manager", "secrets manager", "pyspark", "spark",
    "sql", "databricks",
]

# Minimum number of matched skills for a job to be considered "high match"
# and pushed to you. Lower this if you're getting too few results.
MIN_SKILL_MATCHES = 3

MAX_DAYS_OLD = 2         # only look at postings from the last 2 days
RESULTS_PER_QUERY = 20   # how many results to pull per search query
LOCATION = "India"


# --------------------------------------------------------------------------
# CORE LOGIC
# --------------------------------------------------------------------------

def load_seen_jobs():
    if os.path.exists(SEEN_JOBS_FILE):
        with open(SEEN_JOBS_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen_jobs(seen):
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def fetch_adzuna_jobs(query):
    """Query the Adzuna API for a single search term, India, recent postings."""
    url = f"https://api.adzuna.com/v1/api/jobs/in/search/1"
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "what": query,
        "where": LOCATION,
        "max_days_old": MAX_DAYS_OLD,
        "results_per_page": RESULTS_PER_QUERY,
        "content-type": "application/json",
    }
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json().get("results", [])
    except requests.RequestException as e:
        print(f"[warn] Adzuna query failed for '{query}': {e}")
        return []


def score_job(job):
    """Count how many of your skills appear in the job title + description."""
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    matched = [s for s in MY_SKILLS if s in text]
    return len(set(matched)), sorted(set(matched))


def format_message(job, score, matched_skills):
    title = job.get("title", "Untitled role")
    company = job.get("company", {}).get("display_name", "Unknown company")
    location = job.get("location", {}).get("display_name", "India")
    url = job.get("redirect_url", "")
    created = job.get("created", "")[:10]

    skills_str = ", ".join(matched_skills) if matched_skills else "n/a"

    return (
        f"🎯 <b>{title}</b>\n"
        f"🏢 {company}\n"
        f"📍 {location}\n"
        f"🗓️ Posted: {created}\n"
        f"✅ Skill match ({score}): {skills_str}\n"
        f"🔗 <a href=\"{url}\">Apply here</a>"
    )


def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[warn] Telegram not configured, skipping notification. Message was:")
        print(text)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, data=payload, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[warn] Telegram send failed: {e}")


def main():
    if os.path.exists(PAUSE_FILE):
        print("[info] pause.flag found -- job bot is paused. Exiting without doing anything.")
        sys.exit(0)

    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        print("[error] Missing ADZUNA_APP_ID / ADZUNA_APP_KEY environment variables.")
        sys.exit(1)

    seen = load_seen_jobs()
    new_seen = set(seen)
    new_matches = 0

    for query in SEARCH_QUERIES:
        jobs = fetch_adzuna_jobs(query)
        print(f"[info] '{query}': {len(jobs)} results")

        for job in jobs:
            job_id = str(job.get("id"))
            if not job_id or job_id in seen:
                continue

            score, matched_skills = score_job(job)
            new_seen.add(job_id)  # mark seen regardless of score, so we don't re-check it

            if score >= MIN_SKILL_MATCHES:
                msg = format_message(job, score, matched_skills)
                send_telegram_message(msg)
                new_matches += 1
                time.sleep(1)  # gentle on Telegram rate limits

        time.sleep(1)  # gentle on Adzuna rate limits

    save_seen_jobs(new_seen)
    print(f"[info] Done. {new_matches} new high-match job(s) sent.")


if __name__ == "__main__":
    main()
