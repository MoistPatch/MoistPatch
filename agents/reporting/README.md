# Agent 11 — Daily Reporting

Reads from Agent 1C's SQLite database and emails a structured daily report
of competitor prices, changes, anomalies, and data-quality stats.

This is a **read-only** consumer of the price database — it never modifies
prices, never scrapes, never makes external requests other than SMTP.

---

## What's in a report

- **Key metrics** — SKUs tracked, competitors tracked, scans OK/failed, success rate
- **Current prices by SKU** — every competitor's most-recent price, side-by-side,
  with the cheapest highlighted (in-stock preferred)
- **Price changes in the window** (default 24h) — sorted by magnitude
- **Anomalies** — high/medium severity flags from the z-score + rapid-change detector
- **Scrape failures** — grouped by competitor with last error
- **Data quality** — avg extractor confidence → hallucination risk band
  (very low / low / moderate / elevated / high), plus audit chain integrity check

Both an HTML (mail-client-safe inline CSS) and plain-text body are sent so
every recipient client renders something readable.

---

## Quick start

```bash
# from the repo root
source .venv/bin/activate
pip install -r requirements.txt

# 1. (one time) populate demo data so you can preview the email:
python -m agents.reporting demo-data

# 2. Render the demo as text in your terminal:
python -m agents.reporting render-demo

# 3. Save the demo as HTML for browser preview:
python -m agents.reporting render-demo --format html --out /tmp/preview.html
open /tmp/preview.html   # or xdg-open / start

# 4. Render the REAL report (against whatever 1C has scraped):
python -m agents.reporting render --hours 24

# 5. Dry-run an email (renders, but doesn't send):
python -m agents.reporting send --to sam_tad@hotmail.com --dry-run

# 6. Actually send (requires SMTP credentials — see below):
export SMTP_USER='neuralhardware.bot@gmail.com'
export SMTP_PASS='abcdefghijklmnop'        # Gmail App Password, 16 chars no spaces
python -m agents.reporting send --to sam_tad@hotmail.com
```

---

## Setting up Gmail to send

The agent uses your Gmail account as the outbound mail server. You **must
use a Gmail App Password**, not your normal account password.

1. Go to https://myaccount.google.com/security and enable 2-Step Verification.
2. Go to https://myaccount.google.com/apppasswords.
3. Generate a new App Password — name it "Neural Hardware Agent 11".
4. Copy the 16-character password (it will only be shown once).
5. Export the env vars **on the machine that will run cron**:

```bash
# in ~/.profile or systemd EnvironmentFile or your secrets manager
export SMTP_USER='your.account@gmail.com'
export SMTP_PASS='abcdabcdabcdabcd'
# Optional:
export SMTP_FROM_NAME='Neural Hardware Agent 11'
export REPORT_BCC='audit@neuralhardware.com.au'   # spec-required BCC for compliance
```

⚠️ **Never** commit these to git. The agent reads them from the environment
only. There are no credentials in the codebase.

---

## Schedule it for 06:00 daily

Add this line to your crontab (`crontab -e`). It runs every day at 06:00
local time, sends to `sam_tad@hotmail.com`, and appends output to a log:

```cron
0 6 * * *  cd /path/to/MoistPatch && /path/to/MoistPatch/.venv/bin/python -m agents.reporting send --to sam_tad@hotmail.com >> /var/log/nh-reporting.log 2>&1
```

Make sure the cron environment has `SMTP_USER` / `SMTP_PASS` — cron's
environment is minimal. Either:

- put `SMTP_USER=...` / `SMTP_PASS=...` at the top of the crontab itself, or
- `source ~/.profile` in the cron command, or
- use a systemd timer with an `EnvironmentFile`:

```ini
# /etc/systemd/system/nh-reporting.service
[Service]
Type=oneshot
WorkingDirectory=/path/to/MoistPatch
EnvironmentFile=/etc/neuralhardware/smtp.env
ExecStart=/path/to/MoistPatch/.venv/bin/python -m agents.reporting send --to sam_tad@hotmail.com

# /etc/systemd/system/nh-reporting.timer
[Timer]
OnCalendar=*-*-* 06:00:00
Persistent=true
```

---

## CLI reference

```
python -m agents.reporting [--data-dir DIR] <command>

Commands:
  render           render the report against the real DB
                   --hours N            time window (default 24)
                   --sku NH-RTX5090     filter to specific SKU(s); repeatable
                   --format text|html
                   --out PATH           write HTML to file

  send             render and email the report
                   --to ADDRESS         recipient (required)
                   --bcc ADDRESS        optional BCC (or REPORT_BCC env var)
                   --hours N
                   --sku NH-RTX5090
                   --dry-run            print to stdout instead of sending

  demo-data        populate the DB with clearly-labelled DEMO rows
                   (RTX 5090 across 4 retailers + 2 other SKUs)

  render-demo      render with DEMO banner (refuses to send by default)
                   same options as `render`
```

---

## Safety guards

- `send` refuses to deliver if the report is tagged DEMO unless you pass
  `force_demo=True` in code (no CLI flag — too easy to fat-finger)
- `SmtpConfig.from_env()` raises with a clear error if `SMTP_USER` /
  `SMTP_PASS` are missing — no silent fallback to anonymous SMTP
- Templates auto-escape HTML to prevent injection if SKUs or competitor
  names ever contain HTML-special characters
- All emails carry an `X-Agent: neural-hardware/price-reporter-11` header
  so your inbox rules / SIEM can recognise agent traffic

---

## Sample output

See `docs/sample-report.html` for a rendered example. Open it in a
browser to preview what the email will look like.

---

## Tests

```bash
python -m unittest tests.test_reporting -v
```

10 tests cover: DB compilation, cheapest-in-stock logic, missing-DB error
path, hallucination risk bands, HTML/text rendering, demo banner, SMTP
config from env (success + missing), MIME multipart structure, and the
"refuse to send DEMO" safety guard.
