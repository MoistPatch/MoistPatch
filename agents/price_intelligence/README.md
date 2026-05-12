# Agent 1C — Competitor Price Intelligence

Monitors competitor product pages, extracts and validates prices,
detects price changes and statistical anomalies, and records every action
to a tamper-evident audit log.

This is the **first real agent** of the Neural Hardware multi-agent system.
It is fully runnable and tested — no mocks.

---

## What it does

For each (competitor, SKU) pair in `config/competitors.yaml`:

1. **Checks `robots.txt`** for the host (cached in-memory)
2. **Waits a random 5–15 seconds** between requests to the same competitor
3. **Fetches the product page** over HTTPS (no credentials, no cookies)
4. **Extracts the price** through a confidence-ranked chain:
   - `jsonld` — schema.org `Product` / `Offer` (most reliable, conf 0.98)
   - `opengraph` — `product:price:amount` meta tag (conf 0.92)
   - `microdata` — `itemprop="price"` (conf 0.88)
   - `selector` — per-site CSS selector if configured (conf 0.80)
   - `regex` — last-resort number scan (conf 0.40)
5. **Hard-validates the result**:
   - currency must equal `expected_currency` (default AUD)
   - price must be in `[expected_price_min, expected_price_max]`
   - if any structured method declares the wrong currency, extraction is
     aborted entirely — we never fall back to assuming AUD on a USD page
6. **Stores the price point** in SQLite
7. **Detects a price change** vs. the previous observation
8. **Runs anomaly detection** against the 30-day rolling history:
   - rapid change (>25% in 24h) → severity `high`
   - z-score outlier (|z| ≥ 2.5) → severity `medium`/`high`
9. **Appends every action** to a hash-chained JSONL audit log

---

## Quick start

```bash
# from the repo root
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Edit config/competitors.yaml — set real product URLs, then `enabled: true`
# 2. List what's configured:
python3 -m agents.price_intelligence list

# 3. Run a one-shot scan:
python3 -m agents.price_intelligence scan

# 4. Show recent changes:
python3 -m agents.price_intelligence changes --hours 24

# 5. Inspect history for one SKU:
python3 -m agents.price_intelligence history NH-RTX5090 Mwave --days 30

# 6. Verify the audit log is untampered:
python3 -m agents.price_intelligence verify-audit
```

## Run on a schedule

Drop this in your crontab to scan every 5 minutes (matches the system-wide spec):

```cron
*/5 * * * * cd /path/to/MoistPatch && /path/to/MoistPatch/.venv/bin/python -m agents.price_intelligence scan >> /var/log/nh-price.log 2>&1
```

Or use systemd timers / Kubernetes CronJob in production.

---

## Spec compliance

| Spec requirement | Implementation |
|---|---|
| "Detect price changes within 15 minutes" | Run every 5 min via cron; `PriceChange` row emitted on every change |
| "99.5% accuracy" | Confidence-ranked extraction + hard validation on every result |
| "Validate all prices against source HTML" | `extractor.py:_validate_against_sku` — currency + range checks |
| "Respect robots.txt" | `RobotsCache` in `scraper.py` checks before every fetch |
| "Random delay 5-15s" | `random.uniform(rate_limit_min_s, rate_limit_max_s)` per-host |
| "No credential reuse" | Scraper sends only User-Agent + Accept headers, no auth |
| "Validate extracted values against expected format" | Pydantic models + decimal precision + currency code regex |
| "Full audit trail" | `AuditLog` — append-only JSONL with SHA-256 hash chain, tamper-evident |
| "Agent/human distinguishability" | Every audit entry tagged `actor_type: "agent"` |
| "Rate limited to avoid IP bans" | Per-competitor serialised requests + jittered delay + 429 backoff |
| "Hard validation layer" | All extractions go through `_validate_against_sku` before storage |

---

## Files

```
agents/price_intelligence/
├── __init__.py
├── __main__.py        # CLI entrypoint  (python -m agents.price_intelligence ...)
├── agent.py           # PriceIntelligenceAgent — orchestrates scrape→store→detect
├── anomaly.py         # rapid-change + z-score anomaly detector
├── audit.py           # append-only JSONL with SHA-256 hash chain
├── extractor.py       # JSON-LD → OpenGraph → microdata → selector → regex
├── models.py          # Pydantic data models (Competitor, Sku, PricePoint, …)
├── scraper.py         # async httpx scraper, robots.txt, jittered delay, retries
└── storage.py         # SQLite persistence (price_points, price_changes, scrape_failures)
```

---

## Tests

```bash
python3 -m unittest tests.test_price_intelligence -v
```

13 tests cover: JSON-LD/OpenGraph/microdata/selector/regex extraction,
out-of-range rejection, wrong-currency rejection, comma/dollar-sign
normalisation, anomaly detection (rapid change + z-score + stable),
SQLite round-trip, and audit-chain tamper detection.

---

## Audit log format

Each line in `data/audit.jsonl`:

```json
{
  "prev_hash":  "0000…0000",
  "entry_hash": "9f2e…7c41",
  "ts":         "2026-05-12T12:17:34.942909+00:00",
  "actor_type": "agent",
  "agent":      "price-intelligence-1c",
  "action":     "scan_started",
  "params":     {"sku_count": 5},
  "result":     {},
  "authorization": null
}
```

`entry_hash = sha256(prev_hash + canonical_json(entry without entry_hash))`

Modifying any historical line breaks all subsequent hashes — detectable
via `python -m agents.price_intelligence verify-audit`.

---

## What's intentionally NOT here (yet)

- **Playwright renderer** — JavaScript-heavy sites (Mwave's React frontend on
  some pages) will need this; the `renderer: playwright` field is already in
  the config schema, just not wired up. Add it when you hit your first
  JS-only site.
- **Proxy rotation** — single egress IP for now. Plug in residential proxies
  when you scale past ~50 SKUs/competitor.
- **Notification fan-out** — anomalies and changes are logged + stored, not
  emailed. Agent 11 (Reporting) will consume from the `price_changes` and
  `anomalies` tables.
- **HashiCorp Vault integration** — there are no credentials yet so it's not
  needed. When you add login-walled competitors, route their session cookies
  through Vault per the system spec.
- **Behavioural drift detection** — needs ≥7 days of warmup data first.
  Agent 9 (Memory) will own this once it exists.
