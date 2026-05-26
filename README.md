# Ben's Daily Bay Area Filmmaking Job Scan

A GitHub Actions workflow that runs every morning, asks Claude to search for
SF Bay Area filmmaking jobs posted in the last 24–48 hours, and emails a
formatted digest to **james@walsh.nu** and **walshcben@gmail.com**.

---

## How it works

1. **GitHub Actions** triggers on a `cron` schedule (8 AM Pacific, daily).
2. **`scripts/daily_job_scan.py`** calls the Anthropic API with Claude's
   built-in `web_search_20250305` tool enabled.
3. Claude searches LinkedIn, Indeed, EntertainmentCareers.net, ProductionHub,
   and employer-specific pages, then formats results into two tracks:
   - **Volume Track** – entry-level crew / PA / coordinator roles
   - **Creative Track** – director's assistant, story, AP, documentary, etc.
4. The script emails the digest (plain-text + HTML) via **Gmail SMTP**.

---

## One-time setup — GitHub Secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**
and add all three secrets below.

| Secret | What to put there |
|--------|------------------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key (`sk-ant-…`) |
| `GMAIL_ADDRESS` | The Gmail account that *sends* the email (e.g. `walshcben@gmail.com`) |
| `GMAIL_APP_PASSWORD` | A **Gmail App Password** (16 chars, no spaces) — see below |

### Creating a Gmail App Password

1. Go to your Google Account → **Security**.
2. Under "How you sign in to Google", enable **2-Step Verification** if not already on.
3. Return to Security → search **"App passwords"** (or visit
   [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)).
4. Create a new app password — name it "Bay Area Job Scan" or similar.
5. Copy the 16-character code and paste it as the `GMAIL_APP_PASSWORD` secret.

> **Note:** App Passwords only appear once — copy it immediately.

---

## Running manually (first test)

1. Open the **Actions** tab in this repo.
2. Select **"Daily Bay Area Filmmaking Job Scan"**.
3. Click **"Run workflow"** → **"Run workflow"**.
4. Watch the logs; an email should arrive within ~2 minutes.

---

## Schedule

The cron is set to `0 15 * * *` UTC, which is:

- **8:00 AM PDT** (April – October)
- **7:00 AM PST** (November – March)

To shift to 8 AM year-round in winter, change the cron to `0 16 * * *` in
`.github/workflows/daily-job-scan.yml` during Pacific Standard Time months.

---

## File structure

```
.github/
  workflows/
    daily-job-scan.yml     # Cron schedule + Actions config
scripts/
  daily_job_scan.py        # Main script (Claude + email)
requirements.txt           # Python dependencies
README.md                  # This file
```

---

## Customising the scan

All search parameters live in `scripts/daily_job_scan.py`:

- **`RECIPIENTS`** — add or remove email addresses
- **`USER_PROMPT`** — tweak role categories, employer list, or output format
- **`MODEL`** — swap to `claude-sonnet-4-6` if you want faster/cheaper runs
- **Cron expression** — in `daily-job-scan.yml` to shift the daily send time
