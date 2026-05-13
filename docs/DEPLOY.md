# Deploying Neural Hardware — Live

> Goal: get the storefront on a real domain, and get Agents 1C + 11 running
> on a schedule so you wake up at 6 AM to a real price report from real
> retailers. Lean budget: **A$5–15/month total** (excluding Shopify).

---

## TL;DR — what's going where

| Component | Where | Why | Cost |
|---|---|---|---|
| Storefront `index.html` | **Cloudflare Pages** (or Netlify) | Free, fast, AU edge, free SSL | $0 |
| Agents (1C, 11) | **DigitalOcean Sydney $6 droplet** (or Hetzner/Oracle/Linode) | Persistent disk, cron, SMTP egress | $4–6/mo |
| Database | SQLite on the agent VPS | Zero ops, scales to ~10M rows fine | $0 |
| SMTP | **Gmail with App Password** | Free, deliverable, trusted | $0 |
| Domain | **VentraIP / Cloudflare Registrar** | `.com.au` requires AU ABN | ~$20/yr |
| Real storefront (later) | **Shopify Basic** | Actual commerce, ACL-friendly | A$56/mo |

The static `index.html` in this repo is a brand showcase / preview. The
real e-commerce site is Shopify (per `docs/business-operations.md`).
**Don't try to take payments from the static page.**

---

## What you need before you start

- [ ] A laptop / terminal with `git`, `ssh`
- [ ] An ABN (for `.com.au` domain) — register at business.gov.au if you don't have one (5 min, free)
- [ ] A credit card for the VPS provider
- [ ] A Gmail account you'll use as the sender (you'll generate an App Password from it)
- [ ] The Hotmail address you want reports sent to (e.g. `sam_tad@hotmail.com`)
- [ ] About 45 minutes the first time

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    YOU (your laptop)                         │
│  push code → git → GitHub                                    │
└─────────────────────────────────────────────────────────────┘
              │                              │
              │ git push                     │ git pull
              ▼                              ▼
┌──────────────────────────┐    ┌──────────────────────────────┐
│   GITHUB REPO            │    │  VPS (DigitalOcean SYD, $6/mo)│
│   (private or public)    │    │  ┌───────────────────────────┐ │
└──────────────────────────┘    │  │ systemd timer  (*/5 min)  │ │
              │                  │  │   python -m 1c crawl      │ │
              │ Pages webhook    │  └───────────────────────────┘ │
              ▼                  │  ┌───────────────────────────┐ │
┌──────────────────────────┐    │  │ systemd timer  (06:00)    │ │
│ CLOUDFLARE PAGES         │    │  │   python -m reporting     │ │
│  neuralhardware.com.au   │    │  │   send --to sam_tad@…     │ │
│  (just index.html)       │    │  └───────────────────────────┘ │
└──────────────────────────┘    │     │                          │
                                 │     │ STARTTLS (port 587)      │
                                 │     ▼                          │
                                 │  ┌───────────────────────────┐ │
                                 │  │ smtp.gmail.com            │ │
                                 │  └───────────────────────────┘ │
                                 │           │                    │
                                 │           ▼                    │
                                 │  ┌───────────────────────────┐ │
                                 │  │ sam_tad@hotmail.com       │ │
                                 │  └───────────────────────────┘ │
                                 └──────────────────────────────────┘
```

---

# PART 1 — Deploy the storefront (Cloudflare Pages, 10 min)

The storefront is just one HTML file with no backend. Cloudflare Pages
serves it for free with SSL, on an AU-edge CDN.

### Steps

1. Push this repo to GitHub (private is fine):
   ```bash
   gh repo create neuralhardware --private --source=. --push
   ```
2. Sign up at https://dash.cloudflare.com (free).
3. Sidebar → **Workers & Pages → Create application → Pages → Connect to Git**.
4. Authorise GitHub, pick the `neuralhardware` repo.
5. Build settings: leave **Framework preset = None**, leave build command empty,
   set **Build output directory = `.`** (the root — `index.html` lives there).
6. Click **Save and Deploy**. About 30 seconds later you have a URL like
   `https://neuralhardware-x7q.pages.dev`.
7. Open it. The storefront should look identical to the local preview.

### Hook up your custom domain

1. Buy `neuralhardware.com.au` from https://ventraip.com.au (~A$19/2yr).
   You need an ABN.
2. In Cloudflare Pages → Custom domains → **Add a custom domain** →
   `neuralhardware.com.au`.
3. Cloudflare gives you two `CNAME` values. Add them at VentraIP DNS panel.
4. Wait 5–60 min for DNS propagation. SSL cert is automatic.

Done. The site is live at `https://neuralhardware.com.au`.

---

# PART 2 — Deploy the agents (DigitalOcean droplet, 30 min)

### 2.1 Provision the VPS

1. Sign up at https://digitalocean.com (use a referral code for $200 free credit).
2. **Create → Droplets**:
   - Region: **Sydney 1 (SYD1)**
   - Image: **Ubuntu 24.04 LTS x64**
   - Size: **Basic → Regular Intel → $6/mo (1 GB / 1 vCPU / 25 GB SSD)**
   - Authentication: **SSH key** (paste your `~/.ssh/id_ed25519.pub`)
   - Hostname: `nh-agents`
   - Click **Create Droplet**. Wait ~60 s.
3. Copy the IPv4 address. SSH in:
   ```bash
   ssh root@<IP>
   ```

### 2.2 Hardening (5 min)

Create a non-root user, lock down SSH:
```bash
adduser nh --disabled-password --gecos ""
usermod -aG sudo nh
mkdir -p /home/nh/.ssh
cp /root/.ssh/authorized_keys /home/nh/.ssh/
chown -R nh:nh /home/nh/.ssh
chmod 700 /home/nh/.ssh && chmod 600 /home/nh/.ssh/authorized_keys

# Disable root login and password auth
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart sshd
```

Open a NEW terminal window before closing this one and verify:
```bash
ssh nh@<IP>     # must work
```

If it doesn't, don't close the first session — fix `authorized_keys`.

### 2.3 Install system dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git sqlite3 ufw

# Basic firewall
sudo ufw allow OpenSSH
sudo ufw --force enable
```

### 2.4 Clone the repo and install Python deps

```bash
cd ~
git clone https://github.com/<your-user>/neuralhardware.git
cd neuralhardware
git checkout claude/build-ai-agent-zGcUz   # or `main` once you merge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Quick sanity check
python -m unittest discover tests           # expect 42 tests, all OK
python -m agents.price_intelligence list    # should show 19 competitors
```

### 2.5 Get a Gmail App Password

1. Go to https://myaccount.google.com/security.
2. Turn on **2-Step Verification** (mandatory before you can create App Passwords).
3. Go to https://myaccount.google.com/apppasswords.
4. App name: `Neural Hardware Agent 11`. Click Create.
5. Copy the 16-character password — Google only shows it once.

### 2.6 Store credentials safely

Use a systemd `EnvironmentFile` so secrets are owned by root, mode 0600,
never in shell history, never in the codebase:

```bash
sudo mkdir -p /etc/neuralhardware
sudo tee /etc/neuralhardware/smtp.env > /dev/null <<'EOF'
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your.address@gmail.com
SMTP_PASS=abcdabcdabcdabcd
SMTP_FROM_NAME=Neural Hardware Agent 11
REPORT_BCC=
EOF
sudo chmod 600 /etc/neuralhardware/smtp.env
sudo chown root:root /etc/neuralhardware/smtp.env
```

### 2.7 Test the agents manually first

```bash
cd ~/neuralhardware
source .venv/bin/activate

# (a) Crawl ONE small retailer with a tiny budget
python -m agents.price_intelligence crawl "PC Case Gear" --limit 5

# (b) See what landed in the DB
python -m agents.price_intelligence discovered --limit 20

# (c) Render the email body to your terminal — no send yet
sudo bash -c '
  set -a; source /etc/neuralhardware/smtp.env; set +a
  /home/nh/neuralhardware/.venv/bin/python -m agents.reporting \
      --data-dir /home/nh/neuralhardware/data \
      send --to sam_tad@hotmail.com --dry-run
'

# (d) Real send — small RTX-5090-only filter so the test email isn't huge
sudo bash -c '
  set -a; source /etc/neuralhardware/smtp.env; set +a
  /home/nh/neuralhardware/.venv/bin/python -m agents.reporting \
      --data-dir /home/nh/neuralhardware/data \
      send --to sam_tad@hotmail.com
'
```

Check your Hotmail inbox. Subject will be `[Neural Hardware] Daily
price report — 2026-MM-DD`. Check spam if it's not in the inbox.

If you got the email, you're 90% done. Now automate the schedule.

### 2.8 Install systemd services + timers

Two timers: one runs the price scan every 5 minutes, one runs the
reporter at 06:00 AEST daily.

```bash
sudo tee /etc/systemd/system/nh-crawl.service > /dev/null <<'EOF'
[Unit]
Description=Neural Hardware - price intelligence crawl
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=nh
Group=nh
WorkingDirectory=/home/nh/neuralhardware
EnvironmentFile=/etc/neuralhardware/smtp.env
ExecStart=/home/nh/neuralhardware/.venv/bin/python -m agents.price_intelligence crawl "PC Case Gear" --limit 25
Nice=10
EOF

sudo tee /etc/systemd/system/nh-crawl.timer > /dev/null <<'EOF'
[Unit]
Description=Run nh-crawl every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Unit=nh-crawl.service
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo tee /etc/systemd/system/nh-report.service > /dev/null <<'EOF'
[Unit]
Description=Neural Hardware - daily price report
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=nh
Group=nh
WorkingDirectory=/home/nh/neuralhardware
EnvironmentFile=/etc/neuralhardware/smtp.env
ExecStart=/home/nh/neuralhardware/.venv/bin/python -m agents.reporting send --to sam_tad@hotmail.com
EOF

sudo tee /etc/systemd/system/nh-report.timer > /dev/null <<'EOF'
[Unit]
Description=Send daily price report at 06:00 AEST

[Timer]
OnCalendar=*-*-* 06:00:00 Australia/Sydney
Persistent=true
Unit=nh-report.service

[Install]
WantedBy=timers.target
EOF

# Set system timezone to AEST so the calendar lines up
sudo timedatectl set-timezone Australia/Sydney

# Enable + start the timers
sudo systemctl daemon-reload
sudo systemctl enable --now nh-crawl.timer
sudo systemctl enable --now nh-report.timer

# Confirm they're scheduled
systemctl list-timers nh-*
```

You should see both timers listed with the next-run column showing
when they'll fire.

> The `nh-crawl.service` above only crawls **one** retailer per
> invocation. To cover more, either add multiple `ExecStart=` lines
> with different competitor names, or write a small wrapper script
> that rotates through retailers (one per 5-min slot). With 19
> retailers and 5-min slots, you'd touch every retailer every ~95 min.

### 2.9 Verify the first run

```bash
# Trigger a one-off run right now
sudo systemctl start nh-crawl.service
sudo systemctl start nh-report.service

# Tail the logs
sudo journalctl -u nh-crawl.service -n 50 --no-pager
sudo journalctl -u nh-report.service -n 50 --no-pager

# Inspect the DB
sqlite3 /home/nh/neuralhardware/data/prices.db \
  "SELECT competitor, COUNT(*), SUM(in_stock) FROM price_points GROUP BY competitor"

# Verify the audit chain is intact
cd /home/nh/neuralhardware
source .venv/bin/activate
python -m agents.price_intelligence verify-audit
```

---

# PART 3 — Monitoring & maintenance

### 3.1 Log rotation

`journalctl` rotates by default but caps disk at ~10% of `/var/log`.
Tighten it explicitly:

```bash
sudo mkdir -p /etc/systemd/journald.conf.d
sudo tee /etc/systemd/journald.conf.d/nh.conf > /dev/null <<'EOF'
[Journal]
SystemMaxUse=500M
MaxRetentionSec=30day
EOF
sudo systemctl restart systemd-journald
```

### 3.2 Failure alert (optional but recommended)

If a timer service fails three times, you want to know. Easiest
approach: add an `OnFailure=` hook that emails you.

```bash
sudo tee /etc/systemd/system/nh-failure-email@.service > /dev/null <<'EOF'
[Service]
Type=oneshot
User=nh
EnvironmentFile=/etc/neuralhardware/smtp.env
ExecStart=/usr/bin/python3 -c "import smtplib,ssl,os; \
 from email.message import EmailMessage; \
 m=EmailMessage(); \
 m['From']=os.environ['SMTP_USER']; m['To']='sam_tad@hotmail.com'; \
 m['Subject']='[Neural Hardware] AGENT FAILURE: $1'; \
 m.set_content('Service $1 failed on $(hostname). Check journalctl -u $1'); \
 s=smtplib.SMTP(os.environ['SMTP_HOST'],int(os.environ['SMTP_PORT'])); \
 s.starttls(context=ssl.create_default_context()); \
 s.login(os.environ['SMTP_USER'],os.environ['SMTP_PASS']); s.send_message(m); s.quit()"
EOF

# Add OnFailure= to both services
sudo sed -i '/^\[Unit\]/a OnFailure=nh-failure-email@%n.service' \
  /etc/systemd/system/nh-crawl.service \
  /etc/systemd/system/nh-report.service
sudo systemctl daemon-reload
```

### 3.3 Database backup

SQLite is one file. Back it up nightly to the same box (and ideally off-box):

```bash
sudo tee /etc/systemd/system/nh-backup.service > /dev/null <<'EOF'
[Service]
Type=oneshot
User=nh
WorkingDirectory=/home/nh/neuralhardware
ExecStart=/bin/bash -c 'mkdir -p /home/nh/backups && \
  sqlite3 data/prices.db ".backup /home/nh/backups/prices-$(date +%%Y%%m%%d).db" && \
  find /home/nh/backups -name "prices-*.db" -mtime +30 -delete'
EOF
sudo tee /etc/systemd/system/nh-backup.timer > /dev/null <<'EOF'
[Timer]
OnCalendar=*-*-* 05:30:00 Australia/Sydney
Persistent=true
[Install]
WantedBy=timers.target
EOF
sudo systemctl daemon-reload && sudo systemctl enable --now nh-backup.timer
```

For off-box: `rclone` to Backblaze B2 ($0.005/GB/mo), or `git push`
the backups dir to a private GitHub repo on a cron.

### 3.4 Deploy updates

When you change code on your laptop:
```bash
# laptop
git push origin claude/build-ai-agent-zGcUz   # or main once merged

# VPS
cd ~/neuralhardware
git pull
source .venv/bin/activate
pip install -r requirements.txt          # in case deps changed
sudo systemctl restart nh-crawl.timer nh-report.timer
```

Or wire up a `git pull` cron / GitHub Actions deploy webhook if you
push often.

---

# PART 4 — When to upgrade (you probably won't need to for months)

| Symptom | Upgrade |
|---|---|
| Retailers Cloudflare-block your VPS IP | Add Playwright with real Chromium (`pip install playwright; playwright install chromium`) and a residential proxy ($10–30/mo) |
| DB > 5 GB / queries slow | Move from SQLite to managed Postgres (Neon free tier, or DO managed Postgres $15/mo) |
| Need to crawl > 100k SKUs/day | Split: one VPS per region, shared Postgres, queue (Redis) |
| Want a real orchestrator | Implement Agent 0 from the spec — FastAPI + LangGraph |
| Want zero ops | Move agents to GitHub Actions scheduled workflows + Turso (hosted SQLite) — viable up to ~10 retailers |

---

# Troubleshooting

### Email not arriving

```bash
sudo journalctl -u nh-report.service -n 100 --no-pager
```

Common causes:
- **`535-5.7.8 Username and Password not accepted`** — App Password wrong/expired. Regenerate at https://myaccount.google.com/apppasswords.
- **`5.7.0 Authentication Required`** — 2FA not enabled on the Gmail account.
- **In Hotmail spam folder** — first email or two often goes to junk. Mark as Not Junk; future ones land in inbox.
- **Service shows `refusing to send DEMO report`** — you have demo data in the DB. Either run a real crawl or `rm /home/nh/neuralhardware/data/prices.db` and start fresh.

### Crawl returns 0 products for a retailer

```bash
sqlite3 data/prices.db \
  "SELECT competitor, http_status, error FROM scrape_failures
   WHERE failed_at > datetime('now','-1 hour') ORDER BY id DESC"
```

- **HTTP 403 / 503** → Cloudflare. That retailer needs Playwright.
- **HTTP 404 on sitemap.xml** → check robots.txt for the real sitemap URL,
  update `sitemap_url` in `config/competitors.yaml`.
- **"no schema" skips** → product pages don't have JSON-LD. Phase 2:
  Playwright + custom CSS selectors.

### Timer not firing

```bash
systemctl list-timers nh-*
systemctl status nh-crawl.timer nh-report.timer
```

- Make sure both `.timer` files have `[Install]` section and you ran
  `systemctl enable`.
- Check system timezone: `timedatectl`. Must show `Australia/Sydney`.

### VPS keeps running out of RAM

A 1 GB droplet handles this workload but Playwright (if added later) needs
2 GB. Upgrade to the $12 droplet — instant, no migration.

---

# Cost summary

| Line item | Monthly | Annual |
|---|---|---|
| DigitalOcean SYD droplet ($6) | A$9 | A$108 |
| Domain `neuralhardware.com.au` | — | A$20 |
| Cloudflare Pages | $0 | $0 |
| Gmail SMTP | $0 | $0 |
| **Subtotal — agents + brand** | **A$9** | **A$128** |
| Shopify Basic (when ready) | A$56 | A$672 |
| **Total once Shopify is live** | **A$65** | **A$800** |

---

# Checklist — first launch

- [ ] Domain registered (`neuralhardware.com.au`)
- [ ] Cloudflare Pages site deployed and on custom domain
- [ ] VPS provisioned in SYD region
- [ ] Non-root user created, root login disabled
- [ ] Repo cloned, venv created, tests passing (42/42)
- [ ] Gmail App Password generated
- [ ] `/etc/neuralhardware/smtp.env` created (mode 0600)
- [ ] First manual crawl succeeded
- [ ] First manual email arrived (check spam first)
- [ ] `nh-crawl.timer` enabled, fires every 5 min
- [ ] `nh-report.timer` enabled, fires at 06:00 AEST
- [ ] `nh-backup.timer` enabled
- [ ] Failure alert hook installed
- [ ] First 06:00 email lands in `sam_tad@hotmail.com` (next morning)
