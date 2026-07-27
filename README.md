# AWS Data Engineer Job Bot (India)

Fetches recent AWS Data Engineer / PySpark / Databricks job postings in India
from Adzuna, scores them against your skillset, and pushes high-match new
listings to your Telegram, every 2 hours, for free, via GitHub Actions.

**It does not auto-apply.** It finds and ranks jobs and sends you a one-tap
link so you can apply within minutes of posting — without the account-ban
risk or "spammy generic application" downside of full auto-submission.

---

## One-time setup (~15 minutes)

### 1. Get a free Adzuna API key
1. Go to https://developer.adzuna.com/ and register.
2. Copy your `app_id` and `app_key` from the dashboard.

### 2. Create a Telegram bot (for notifications)
1. In Telegram, message **@BotFather** → `/newbot` → follow prompts.
2. Copy the **bot token** it gives you.
3. Send any message to your new bot (so it can message you back).
4. Get your **chat ID**: visit
   `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   in a browser after messaging the bot, and find `"chat":{"id": ...}`.

### 3. Create a GitHub repo and upload these files
1. Create a new **private** GitHub repo (private keeps your job search low-key).
2. Upload all files in this folder, keeping the `.github/workflows/` structure intact.

### 4. Add your secrets
In your repo: **Settings → Secrets and variables → Actions → New repository secret**.
Add all four:
- `ADZUNA_APP_ID`
- `ADZUNA_APP_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

### 5. Enable and test
- Go to the **Actions** tab in your repo, enable workflows if prompted.
- Click **"AWS Data Engineer Job Bot" → Run workflow** to trigger it manually once.
- Check your Telegram — you should start getting matches within a minute or two.

That's it. It now runs automatically every 2 hours, 24/7, for free.

---

## Pausing and resuming

To **pause**: create an empty file named `pause.flag` in the repo root and commit it.
The bot checks for this file first and exits immediately without fetching or
notifying anything, whenever it's present.

To **resume**: delete `pause.flag` and commit.

You can do this from GitHub's web UI directly (Add file → Create new file →
name it `pause.flag` → commit), no local setup needed.

---

## Tuning it

Open `fetch_jobs.py` and adjust:

- `SEARCH_QUERIES` — add/remove search terms.
- `MIN_SKILL_MATCHES` — lower it (e.g. to 2) if you're getting too few
  results, raise it (e.g. to 4) if you're getting too many loosely-related ones.
- `MAX_DAYS_OLD` — how recent postings must be.
- The cron schedule in `.github/workflows/fetch-jobs.yml` — e.g. change
  `0 */2 * * *` to `0 */1 * * *` for hourly checks.

---

## Why this doesn't auto-submit applications

Most Indian job portals (Naukri, LinkedIn, Indeed) explicitly prohibit
automated form submission in their terms of service, and their anti-bot
systems are built to detect exactly this pattern — the realistic result is
an account flag or ban, not a stream of quiet successful applications.
Beyond the ToS risk, ATS systems and recruiters generally rank generic,
identical auto-submitted applications *lower* than fewer, tailored ones —
so full automation actively works against the shortlisting outcome you
want. This tool gets you the speed advantage (early applicant, near
real-time alerts) while leaving the 10-second "review and click apply"
step with you, which is also your one chance to tailor an answer or
attach a cover note if the posting needs one.
