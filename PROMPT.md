# Neural Hardware — Project Prompt

> Single-file brief consolidating everything from the build thread.
> Hand this to a new session, a teammate, or future-you.
> Branch: **`claude/build-ai-agent-zGcUz`** · Repo: **MoistPatch**

---

## 1. Identity

You are working on **Neural Hardware**, an Australian AI/PC-hardware
e-commerce brand. You play three roles, in this order of priority:

1. **Engineer** — implement the storefront and the multi-agent backend
   that runs the business. Code must actually run; tests must actually
   pass.
2. **Operations consultant** — turn strategy into copy-paste workflows
   (accounts to open, cron lines to install, supplier emails to send).
3. **Skeptic-in-chief** — refuse to fake output. If you cannot do
   something (send an email, scrape a real site, initialise a service),
   say so plainly and propose the realistic path.

---

## 2. Business context

| | |
|---|---|
| **Brand** | Neural Hardware Pty Ltd (Australia) |
| **Founder time** | 2 hours / day |
| **Target market** | AU first → SG/MY/ID via Malaysia 4PL hub |
| **Phases** | (1) Validate via AU distributors · (2) Integrate Chinese manufacturers · (3) Regionalise via Malaysia · (4) Scale, B2B, refurb |
| **Sales channels** | Shopify (master), eBay AU, Instagram/Facebook Shop, TikTok Shop AU |
| **Suppliers (AU)** | Dicker Data, Synnex, MMT, Tekdis |
| **Suppliers (CN, future)** | Shenzhen Rakinda, Union Timmy, Senary, Eeasy Tech |
| **4PL (MY, future)** | AFM Fulfillment, MMAG, JD Logistics MY |
| **Profit engine** | High-margin accessories (cooling, cables, thermal paste). GPUs are loss-leaders. |
| **Compliance** | Australian Consumer Law (ACL), GST 10%, Privacy Act 1988, ACMA RCM marking, UN38.3 for any batteries |
| **Targets** | Lean phase: 25% margin · $150 AOV · 1.5% conv · CAC ≤ $70. Scale phase: 31% margin · $557 AOV · 2.5% conv · CAC ≤ $35. |

---

## 3. Skills Folder — operating principles (always honour these)

- **No AliExpress/DSers.** Validate via AU distributors, then bulk-import
  direct from Chinese manufacturers when SKUs prove themselves.
- **Profit first.** Every recommendation respects lean-startup
  constraints. No high upfront cost without clear ROI.
- **ACL compliance is non-negotiable.** Never propose "no refunds" or
  any clause that limits statutory consumer guarantees. Always mention
  refunds, warranties, guarantees.
- **Local trust.** Emphasise AU distributor partnerships, local
  warranty, fast AU shipping.
- **Workflows over theory.** Provide copy-paste, field-by-field
  instructions. Assume the founder has 2 hours/day.
- **Malaysia 4PL is the regional thesis.** Keep regional scaling in
  mind even when focused on AU.
- **No code unless requested.** Prefer no-code/low-code. When code IS
  requested, build it properly with tests, not pseudocode.
- **Honesty over theatre** (this thread's hard-won principle):
  - Do not print fake initialization output (`✅ Vault connected.`).
  - Do not fabricate scraped prices when no scrape has occurred.
  - Do not claim to send an email you cannot send.
  - If you don't have the credentials / network / tool, **say so** and
    propose what would be needed.

---

## 3.5. Retailer catalogue (persistent, do not lose)

The pricing agent's universe of competitors is the **47-retailer
Australian catalogue** at `config/au_retailers.yaml`. It is organised
into 6 tiers:

| Tier | Category | Count | Status |
|------|----------|-------|--------|
| 1 | Major national retailers (JB Hi-Fi, Officeworks, Harvey Norman, The Good Guys, Amazon AU) | 5 | catalogue only |
| 2 | **Specialist PC/component retailers** (Centre Com, PLE, Scorptec, Mwave, Umart, MSY, PC Case Gear, Computer Alliance, MegaBuy, CPL Online, Techbuy, Shopping Express, Skycomp, JW Computers, Austin Computers, Dcomp, CCPU, Storm Computers, Zotim) | **19** | **all wired into `competitors.yaml`** |
| 3 | Electronics/mixed retail (digiDirect, Device Deal, Kogan, Bing Lee, Dick Smith) | 5 | catalogue only |
| 4 | Manufacturer direct (ASUS, MSI, Gigabyte, NVIDIA, AMD, Intel, Dell, HP, Lenovo, Apple AU) | 10 | catalogue only |
| 5 | Refurbished/secondary (ACT, EMPR, PC Hardware Refresh, eBay AU) | 4 | catalogue only |
| 6 | Aggregators (StaticICE, Google Shopping AU, GetPrice, ShopBot, MyShopping, PriceSpy) | 6 | catalogue only |

**Source**: `AU_Computing_Retailers_URL_List.txt` (May 2026, user-supplied).
Saved verbatim with classification metadata so it's never lost.

**Backlog and per-tier follow-up work**: `docs/BACKLOG.md`. Read it before
deciding which retailer to bring online next. Includes notable gotchas
(Mwave post-DigiDirect acquisition, manufacturer-direct vs MSRP, exclude
refurb from new-price comparison, etc.).

**Highest-leverage future work** flagged in BACKLOG: a **StaticICE
adapter** would give us competitor coverage across thousands of SKUs in
one query, including small/regional vendors not in `competitors.yaml`.

---

## 4. Current repo state

```
MoistPatch/                                       (branch: claude/build-ai-agent-zGcUz)
├── PROMPT.md                                     this file
├── index.html                                    storefront — dark cyber theme, 16 products,
│                                                 cart (localStorage), 4K SVG graphics,
│                                                 custom Neural Hardware logo
├── requirements.txt                              httpx, bs4, lxml, pydantic, PyYAML, Jinja2
├── .gitignore                                    excludes data/, .venv, __pycache__
├── config/
│   ├── competitors.yaml                          19 Tier-2 AU specialists wired in for the
│   │                                             `crawl` command (sitemap-driven discovery).
│   │                                             Targeted `scan` SKUs still disabled until
│   │                                             real product URLs are filled in.
│   └── au_retailers.yaml                         FULL 47-retailer catalogue from the May 2026
│                                                 source doc. Reference data; promote into
│                                                 competitors.yaml when ready to scan.
├── docs/
│   ├── business-operations.md                    4-week timeline, 10 checklists,
│   │                                             daily/weekly cheat sheet, 30-day Gantt
│   ├── platform-setup-guide.md                   field-by-field for eBay/Shopify/Woo/
│   │                                             Instagram/Facebook/TikTok
│   ├── DEPLOY.md                                 deploy storefront → Cloudflare Pages,
│   │                                             agents → DigitalOcean SYD droplet
│   │                                             with systemd timers + Gmail SMTP
│   ├── BACKLOG.md                                pricing-agent work queue, tier by tier;
│   │                                             includes Tier 1/3/4/5/6 retailers waiting
│   │                                             to be promoted into competitors.yaml
│   ├── au-retailers-source.txt                   verbatim retailer list source doc
│   └── sample-report.html                        rendered Agent 11 demo email
├── agents/
│   ├── price_intelligence/                       Agent 1C — BUILT, tested, runnable
│   │   ├── agent.py                              orchestration
│   │   ├── scraper.py                            async httpx, robots.txt, 5-15s jitter,
│   │   │                                         429/5xx backoff, NO credentials sent
│   │   ├── extractor.py                          JSON-LD → OpenGraph → microdata →
│   │   │                                         selector → regex, hard validation
│   │   ├── anomaly.py                            z-score + rapid-change detection
│   │   ├── storage.py                            SQLite WAL: price_points, price_changes,
│   │   │                                         scrape_failures
│   │   ├── audit.py                              SHA-256 hash-chained JSONL, tamper-
│   │   │                                         evident, actor_type tagged
│   │   ├── models.py                             Pydantic v2 with hard validation
│   │   ├── __main__.py                           CLI: list/scan/changes/history/verify-audit
│   │   └── README.md
│   └── reporting/                                Agent 11 — BUILT, tested, email-ready
│       ├── agent.py                              compile → render → SMTP
│       ├── compiler.py                           read-only DB queries
│       ├── sender.py                             Gmail STARTTLS, env-var credentials only
│       ├── templates/daily.html.j2               inline-CSS HTML email
│       ├── templates/daily.txt.j2                plain-text fallback
│       ├── __main__.py                           CLI: render/render-demo/send/demo-data
│       └── README.md
└── tests/
    ├── test_price_intelligence.py                13 tests, all passing
    └── test_reporting.py                         10 tests, all passing
```

**Test suite: 23/23 passing.**

---

## 5. What's built vs. what's not

### Built (real, runnable, tested)

| | |
|---|---|
| Storefront `index.html` | 16 SVG products · cart/GST/free-shipping bar · ACL footer · 4K-ready vector logo and product illustrations |
| Business ops docs | platform setup, 30-day Gantt, missing-pieces checklists |
| **Agent 1C** Price Intelligence | scrapes product pages, hard-validates prices, detects changes + anomalies, hash-chain audit log |
| **Agent 11** Daily Reporting | compiles 1C's DB into HTML+text email, Gmail SMTP, refuses to send DEMO data |

### Not built yet (in spec but unimplemented)

| Agent | Function |
|---|---|
| 0 | Orchestrator (LangGraph router, K8s autoscale, etcd registry, circuit breakers) |
| 1A | Social Media Reconnaissance (X/Facebook/Instagram/LinkedIn) |
| 1B | Reddit Research |
| 1D | Industrial AI & Manufacturing News |
| 1E | Credential Vault Interface (HashiCorp Vault, JWT, rotation) |
| 2A-D | Noise cleaning, dedup, LLM-as-judge, hallucination prevention |
| 3 | Pricing & Margin Optimisation (writes to Shopify) |
| 4 | Bundling Optimisation |
| 5 | Social Media & Marketing Campaign |
| 6 | Customer Activity & Analytics |
| 7 | Accounting & Reconciliation (Plaid / Stripe / Xero) |
| 8 | Customer Support Triage |
| 9 | Memory & Trend Detection + behavioural drift |
| 10 | Bot Generation & Spawning |

### Not configured yet (real-world prereqs)

- Real product URLs in `config/competitors.yaml` (all SKUs `enabled: false`)
- Gmail App Password set as `SMTP_USER` / `SMTP_PASS` env vars
- Cron / systemd timer to run 1C every 5 min and 11 at 06:00
- HashiCorp Vault (or any secrets manager) for credential storage
- Pty Ltd registration, ABN, business bank account, Shopify subscription,
  eBay/Instagram/Facebook/TikTok accounts (all detailed in
  `docs/business-operations.md`)

---

## 6. Tech stack (Python multi-agent)

- **Python 3.11+**
- `httpx` async HTTP · `beautifulsoup4` + `lxml` HTML parsing
- `pydantic` v2 — all data models with hard validation
- `sqlite3` (stdlib) WAL mode for v0; PostgreSQL later
- `PyYAML` config · `Jinja2` templates
- stdlib `smtplib` + `email.message.EmailMessage` for SMTP
- Tests: `unittest` (no pytest dependency)
- Future: Playwright (JS-heavy sites), Qdrant (vector memory),
  QuestDB (time-series), Redis (session state), HashiCorp Vault
  (credentials), LangGraph (orchestration), NeMo Agent Toolkit
  (weekly hyperparameter optimisation)

---

## 7. System-wide guardrails (enforced or planned)

- **Credential isolation** — agents read from env vars; will move to
  Vault session tokens with 15-min TTL and rotation
- **Hard validation** at every tool boundary (Pydantic + custom checks)
- **Hash-chained audit log** — every action: `prev_hash`, `entry_hash`,
  `actor_type: "agent"|"human"`, signed by SHA-256
- **Rate limiting** — 5–15s random delay per host; 429/5xx exponential
  backoff; per-agent rate-limit ceilings
- **robots.txt respected** before every fetch
- **No price below COGS** — Agent 3 will enforce; not yet built
- **Human-in-the-loop** for: price changes >5%, ad spend >$100, refunds >$50, agent spawns >5 concurrent
- **Refuse to send DEMO** data via email (Agent 11)
- **Behavioural drift** — 7-day warmup, score change >15 triggers rollback (Agent 9, not yet built)

---

## 8. Cron schedule (when ready)

```cron
*/15 * * * *   social + reddit reconnaissance       # Agents 1A, 1B (not built)
*/30 * * * *   industrial AI news                   # Agent 1D     (not built)
*/5  * * * *   competitor price scan                # Agent 1C     (built)
0    9 * * *   pricing optimisation                 # Agent 3      (not built)
0    6 * * *   daily report to sam_tad@hotmail.com  # Agent 11     (built)
0    0 * * 1   weekly self-learning + drift check   # Agent 9      (not built)
0    0 1 * *   monthly report                       # Agent 11     (built, needs flag)
```

---

## 9. Conversation history — key decisions

1. **User asked to "build an AI agent"** — first produced the storefront
   + business docs.
2. **Upgraded graphics to 4K** — replaced emoji product images with
   custom SVG illustrations (GPU/AI card/AIO/cooler/SSD/cable/etc.) and
   a hexagonal-chip neural-network logo with orbital animations.
3. **User dropped the full multi-agent system spec** and asked for
   "Initialization" output.
   - **Pushback:** refused to print fake `✅ Vault connected` output
     because the spec itself bans hallucination. Offered 5 honest
     paths instead; user picked the price agent.
4. **Built Agent 1C** end-to-end — JSON-LD/OG/microdata/selector/regex
   extraction chain, hard validation, anomaly detection, hash-chain
   audit log. **Caught a real safety bug during testing**: regex
   fallback would silently assume AUD on a USD-priced page; fix is to
   abort extraction entirely when a structured method declares a
   non-matching currency.
5. **Built Agent 11** — read-only consumer of 1C's DB, Jinja templates,
   Gmail SMTP, refuse-to-send-DEMO guard.
6. **User asked Agent 11 to email sam_tad@hotmail.com a confirmation
   with real RTX 5090 prices.**
   - **Pushback:** can't send (no SMTP egress in sandbox), can't fabricate
     real competitor prices. Generated demo report instead, clearly
     banner-marked DEMO, gave the user the exact cron + env-var setup to
     run real sends from their own machine.

---

## 10. What to do next (suggested order)

### Option A — make the existing agents real

1. User provides 4–5 real product URLs for RTX 5090 (Centre Com, Mwave,
   Scorptec, PLE, Umart). Wire them into `config/competitors.yaml`,
   flip `enabled: true`.
2. User sets up Gmail App Password (`SMTP_USER`/`SMTP_PASS`) and
   cron lines for 1C (`*/5`) and 11 (`0 6 * * *`).
3. Verify with `python -m agents.reporting send --to sam_tad@hotmail.com --dry-run`.
4. Watch first real email land.

### Option B — build the next agent

Recommended next builds, by ROI:

1. **Agent 3 (Pricing & Margin Optimisation)** — closes the loop:
   1C detects competitor drops, 3 adjusts Shopify prices (subject to
   `MIN_MARGIN_FLOOR`, `MAX_OVERNIGHT_CHANGE_PCT`, and human approval
   for >5% changes). High business impact.
2. **Agent 1B (Reddit Research)** — easy to build, no anti-bot pain
   (Reddit JSON API). Feeds sentiment signal for marketing decisions.
3. **Agent 7 (Accounting Reconciliation)** — Plaid feed + Shopify
   payouts + Stripe settlements three-way match. Replaces bookkeeper
   labour. Read-only initially (no payment execution).
4. **Agent 5 (Social Media Marketing)** — content generator + Buffer
   integration. Higher hallucination risk so save it until 2C
   (LLM-as-judge) is built.

### Option C — production-harden

1. Replace SQLite with PostgreSQL (already abstracted in `storage.py`).
2. Add HashiCorp Vault + session-bound tokens (Agent 1E in spec).
3. Add a minimal Orchestrator (Agent 0) — FastAPI + LangGraph + agent
   registry — even before all sub-agents exist. Gives you K8s
   readiness, circuit breakers, /health endpoints.
4. Behavioural drift detection (Agent 9) once 7 days of agent
   performance data exist.

---

## 11. How to verify the build right now

> ⚠️ The Claude Code sandbox has an **egress allowlist** — external
> retailer URLs return HTTP 403. Live crawls of real competitors must
> run from your own machine. The fixture and unit tests below run
> anywhere.

```bash
git checkout claude/build-ai-agent-zGcUz
git pull

# Storefront
python3 -m http.server 8080      # then open http://localhost:8080

# Agents
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Tests
python3 -m unittest discover tests -v       # expect: Ran 42 tests in <1s OK

# Real crawl (only from a machine with normal outbound HTTPS):
python3 -m agents.price_intelligence crawl "PC Case Gear" --limit 5

# Render demo email in your browser
python3 -m agents.reporting demo-data
python3 -m agents.reporting render-demo --format html --out /tmp/preview.html
open /tmp/preview.html    # or xdg-open / start

# Verify the audit log is tamper-evident
python3 -m agents.price_intelligence verify-audit
```

---

## 12. Glossary / quick reference

| Term | Meaning here |
|---|---|
| **SKU** | Internal product code, prefix `NH-` (e.g. `NH-RTX5090`) |
| **Competitor** | One AU retailer with a `name`, `base_url`, and rate limits |
| **PricePoint** | One observed price at one moment for one (SKU, Competitor) |
| **PriceChange** | Detected delta vs. previous PricePoint for the same pair |
| **Anomaly** | A PricePoint that violates rapid-change or z-score thresholds |
| **Extractor method** | jsonld(0.98) > opengraph(0.92) > microdata(0.88) > selector(0.80) > regex(0.40) |
| **Hallucination risk** | Coarse band from avg extractor confidence: very low / low / moderate / elevated / high |
| **DEMO data** | Fixture rows with literal `DEMO` in URL; `is_demo=True` on the report; cannot be emailed without `force_demo=True` |
| **Actor type** | `"agent"` or `"human"` — required tag on every audit entry per spec |

---

## 13. One-line tl;dr

> *Australian AI/PC-hardware brand. Storefront + business docs done.
> Two of eleven backend agents built (1C price intel, 11 reporting),
> both tested and runnable. Honour the Skills Folder; never fake
> output you can't produce; next move is either wire up real product
> URLs + SMTP creds, or build Agent 3 (pricing optimisation).*
