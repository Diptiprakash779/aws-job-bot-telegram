#!/usr/bin/env python3
"""
AWS Data Engineer Job Bot (India)
----------------------------------
Fetches recent job postings from multiple sources (Adzuna, Jooble,
Arbeitnow, and optionally JSearch/RapidAPI which aggregates LinkedIn,
Indeed, Glassdoor and Google Jobs), scores them against your skillset,
and pushes high-match new listings to you via Telegram.

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
JOOBLE_API_KEY = os.environ.get("JOOBLE_API_KEY")          # optional
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")               # optional (JSearch)
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

# A single combined query used for sources where we want to conserve
# request quota (e.g. JSearch's free tier).
COMBINED_QUERY = "AWS Data Engineer PySpark Databricks"

# Your skillset -- used to score each JD for relevance.
MY_SKILLS = [
    "aws", "glue", "s3", "athena", "mwaa", "airflow", "iam",
    "step function", "step functions", "kms", "vpc", "ec2",
    "secret manager", "secrets manager", "pyspark", "spark",
    "sql", "databricks",
    "transfer family", "eventbridge", "event bridge",
    "iceberg", "cloudwatch", "appflow",
]

# Minimum number of matched skills for a job to be considered "high match"
# and pushed to you. Lower this if you're getting too few results.
MIN_SKILL_MATCHES = 3

MAX_DAYS_OLD = 2         # only look at postings from the last 2 days
RESULTS_PER_QUERY = 20   # how many results to pull per search query
LOCATION = "India"


# --------------------------------------------------------------------------
# STATE
# --------------------------------------------------------------------------

def load_seen_jobs():
    """Returns (seen_ids, seen_fingerprints) -- both sets.
    Supports the old flat-list file format too, for a smooth upgrade."""
    if not os.path.exists(SEEN_JOBS_FILE):
        return set(), set()

    with open(SEEN_JOBS_FILE, "r") as f:
        data = json.load(f)

    if isinstance(data, list):
        # old format: just a list of ids, no fingerprints yet
        return set(data), set()

    return set(data.get("ids", [])), set(data.get("fingerprints", []))


def save_seen_jobs(seen_ids, seen_fingerprints):
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump({
            "ids": sorted(seen_ids),
            "fingerprints": sorted(seen_fingerprints),
        }, f, indent=2)


# --------------------------------------------------------------------------
# SOURCE 1: Adzuna
# --------------------------------------------------------------------------

def fetch_adzuna_jobs(query):
    """Query the Adzuna API for a single search term, India, recent postings.
    Returns a list of normalized job dicts."""
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        return []

    url = "https://api.adzuna.com/v1/api/jobs/in/search/1"
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
        results = resp.json().get("results", [])
    except requests.RequestException as e:
        print(f"[warn] Adzuna query failed for '{query}': {e}")
        return []

    normalized = []
    for job in results:
        normalized.append({
            "source": "Adzuna",
            "id": f"adzuna:{job.get('id')}",
            "title": job.get("title", "Untitled role"),
            "company": job.get("company", {}).get("display_name", "Unknown company"),
            "location": job.get("location", {}).get("display_name", "India"),
            "url": job.get("redirect_url", ""),
            "created": (job.get("created") or "")[:10],
            "description": job.get("description", ""),
        })
    return normalized


# --------------------------------------------------------------------------
# SOURCE 2: Jooble
# --------------------------------------------------------------------------

def fetch_jooble_jobs(query):
    """Query the Jooble API for a single search term, India, recent postings.
    Returns a list of normalized job dicts."""
    if not JOOBLE_API_KEY:
        return []

    url = f"https://jooble.org/api/{JOOBLE_API_KEY}"
    payload = {"keywords": query, "location": LOCATION}
    try:
        resp = requests.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        results = resp.json().get("jobs", [])
    except requests.RequestException as e:
        print(f"[warn] Jooble query failed for '{query}': {e}")
        return []

    normalized = []
    for job in results[:RESULTS_PER_QUERY]:
        normalized.append({
            "source": "Jooble",
            "id": f"jooble:{job.get('id') or job.get('link')}",
            "title": job.get("title", "Untitled role"),
            "company": job.get("company", "Unknown company"),
            "location": job.get("location", "India"),
            "url": job.get("link", ""),
            "created": (job.get("updated") or "")[:10],
            "description": job.get("snippet", ""),
        })
    return normalized


# --------------------------------------------------------------------------
# SOURCE 3: Arbeitnow (free, no key needed, has real remote-job data)
# --------------------------------------------------------------------------

def fetch_arbeitnow_jobs():
    """Query the free Arbeitnow API. No key required. Returns normalized jobs,
    filtered client-side for relevance since Arbeitnow doesn't support
    keyword search server-side."""
    url = "https://www.arbeitnow.com/api/job-board-api"
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        results = resp.json().get("data", [])
    except requests.RequestException as e:
        print(f"[warn] Arbeitnow query failed: {e}")
        return []

    normalized = []
    for job in results:
        title = job.get("title", "")
        desc = job.get("description", "")
        text = f"{title} {desc}".lower()
        # Arbeitnow has no keyword search param, so pre-filter here to
        # avoid pulling in totally unrelated roles (e.g. sales, marketing).
        if not any(k in text for k in ["data engineer", "pyspark", "databricks", "aws data", "big data"]):
            continue

        is_remote = job.get("remote", False)
        location = "Remote" if is_remote else (job.get("location") or "Not specified")

        created_ts = job.get("created_at")
        created_str = time.strftime("%Y-%m-%d", time.gmtime(created_ts / 1000)) if created_ts else ""

        normalized.append({
            "source": "Arbeitnow",
            "id": f"arbeitnow:{job.get('slug')}",
            "title": title or "Untitled role",
            "company": job.get("company_name", "Unknown company"),
            "location": location,
            "url": job.get("url", ""),
            "created": created_str,
            "description": desc,
        })
    return normalized


# --------------------------------------------------------------------------
# SOURCE 4 (optional): JSearch via RapidAPI -- aggregates LinkedIn, Indeed,
# Glassdoor, Google Jobs. Free tier is quota-limited (~200 requests/month),
# so this uses ONE combined query per run instead of looping per keyword.
# Only runs if RAPIDAPI_KEY is set as a secret.
# --------------------------------------------------------------------------

def fetch_jsearch_jobs():
    if not RAPIDAPI_KEY:
        return []

    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    params = {
        "query": f"{COMBINED_QUERY} in India",
        "page": "1",
        "num_pages": "1",
        "date_posted": "3days",
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        resp.raise_for_status()
        results = resp.json().get("data", [])
    except requests.RequestException as e:
        print(f"[warn] JSearch query failed: {e}")
        return []

    normalized = []
    for job in results:
        normalized.append({
            "source": "JSearch (LinkedIn/Indeed/Glassdoor)",
            "id": f"jsearch:{job.get('job_id')}",
            "title": job.get("job_title", "Untitled role"),
            "company": job.get("employer_name", "Unknown company"),
            "location": job.get("job_city") or job.get("job_country") or "India",
            "url": job.get("job_apply_link", ""),
            "created": (job.get("job_posted_at_datetime_utc") or "")[:10],
            "description": job.get("job_description", ""),
        })
    return normalized


# --------------------------------------------------------------------------
# SCORING + NOTIFICATION
# --------------------------------------------------------------------------

def score_job(job):
    """Count how many of your skills appear in the job title + description."""
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    matched = [s for s in MY_SKILLS if s in text]
    return len(set(matched)), sorted(set(matched))


def job_fingerprint(job):
    """Build a normalized (company, title) fingerprint so the SAME job
    posted on multiple sources (e.g. Adzuna AND Jooble) is only ever
    counted/notified once, even though each source gives it a different
    internal ID."""
    def normalize(s):
        s = (s or "").lower().strip()
        # collapse whitespace, drop punctuation that varies between sources
        s = "".join(ch for ch in s if ch.isalnum() or ch.isspace())
        return " ".join(s.split())

    return f"{normalize(job.get('company'))}::{normalize(job.get('title'))}"


def format_message(job, score, matched_skills):
    skills_str = ", ".join(matched_skills) if matched_skills else "n/a"
    return (
        f"🎯 <b>{job['title']}</b>\n"
        f"🏢 {job['company']}\n"
        f"📍 {job['location']}\n"
        f"🌐 Source: {job['source']}\n"
        f"🗓️ Posted: {job['created'] or 'n/a'}\n"
        f"✅ Skill match ({score}): {skills_str}\n"
        f"🔗 <a href=\"{job['url']}\">Apply here</a>"
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


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------

def main():
    if os.path.exists(PAUSE_FILE):
        print("[info] pause.flag found -- job bot is paused. Exiting without doing anything.")
        sys.exit(0)

    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        print("[error] Missing ADZUNA_APP_ID / ADZUNA_APP_KEY environment variables.")
        sys.exit(1)

    seen_ids, seen_fingerprints = load_seen_jobs()
    new_seen_ids = set(seen_ids)
    new_seen_fingerprints = set(seen_fingerprints)
    all_jobs = []

    # Per-keyword sources
    for query in SEARCH_QUERIES:
        adzuna_jobs = fetch_adzuna_jobs(query)
        print(f"[info] Adzuna '{query}': {len(adzuna_jobs)} results")
        all_jobs.extend(adzuna_jobs)
        time.sleep(1)

        jooble_jobs = fetch_jooble_jobs(query)
        print(f"[info] Jooble '{query}': {len(jooble_jobs)} results")
        all_jobs.extend(jooble_jobs)
        time.sleep(1)

    # Sources that don't need per-keyword looping
    arbeitnow_jobs = fetch_arbeitnow_jobs()
    print(f"[info] Arbeitnow: {len(arbeitnow_jobs)} relevant results")
    all_jobs.extend(arbeitnow_jobs)

    jsearch_jobs = fetch_jsearch_jobs()
    if RAPIDAPI_KEY:
        print(f"[info] JSearch: {len(jsearch_jobs)} results")
    all_jobs.extend(jsearch_jobs)

    # Score, dedupe (both by exact id AND by cross-source fingerprint), notify
    new_matches = 0
    duplicates_skipped = 0
    for job in all_jobs:
        job_id = job["id"]
        fingerprint = job_fingerprint(job)

        if not job_id or job_id in new_seen_ids:
            continue  # exact same listing already processed (this run or a past run)

        new_seen_ids.add(job_id)

        if fingerprint in new_seen_fingerprints:
            # same role, different source -- already notified once, skip silently
            duplicates_skipped += 1
            continue

        score, matched_skills = score_job(job)
        new_seen_fingerprints.add(fingerprint)

        if score >= MIN_SKILL_MATCHES:
            msg = format_message(job, score, matched_skills)
            send_telegram_message(msg)
            new_matches += 1
            time.sleep(1)  # gentle on Telegram rate limits

    save_seen_jobs(new_seen_ids, new_seen_fingerprints)
    print(
        f"[info] Done. {len(all_jobs)} total fetched, {new_matches} new high-match job(s) sent, "
        f"{duplicates_skipped} cross-source duplicate(s) skipped."
    )


if __name__ == "__main__":
    main()
