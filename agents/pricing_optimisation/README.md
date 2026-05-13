# Agent 3 — Pricing & Margin Optimisation

Closes the loop from Agent 1C (competitor price intelligence): reads
competitor prices from `data/prices.db`, applies a configured strategy
per SKU, enforces hard margin/MSRP guardrails, queues big changes for
human approval, and emits a Shopify-compatible CSV for bulk price update.

**This agent never calls Shopify directly.** It produces decisions;
the actual price push is either (a) a manual CSV import in Shopify
Admin, or (b) a future Shopify Admin API integration (Phase 2).

---

## Data flow

```
config/our_skus.yaml         Agent 1C's data/prices.db
   │  (COGS, MSRP,                  │  (competitor prices)
   │  current price,                │
   │  margin floor,                 │
   │  strategy)                     │
   └──────────────┬─────────────────┘
                  ▼
        PricingOptimisationAgent
                  │
        ┌─────────┴─────────┐
        │   strategy.py     │  competitive_floor | match_cheapest | margin_target
        └─────────┬─────────┘
                  ▼
        ┌──────────────────┐
        │   guardrails     │  never < min_price · never > MSRP · clamp
        └─────────┬────────┘
                  ▼
        ┌──────────────────┐
        │ classify status  │  no_change | auto_applied | pending_approval | no_data
        └─────────┬────────┘
                  ▼
        data/pricing.db          data/pricing-audit.jsonl
    (pricing_decisions)         (SHA-256 hash chain, actor_type tagged)
                  │
                  ▼
        export-csv → data/shopify-prices.csv
                  │
                  ▼
        Shopify Admin → Products → Import
```

---

## Strategies

| Name | Behaviour |
|------|-----------|
| `competitive_floor` (default) | Match cheapest in-stock; hold floor if competitor is below COGS+margin |
| `match_cheapest` | Always match cheapest (even below floor; guardrails then clamp up) |
| `margin_target` | Anchor on a target gross margin %, ignore competitor pressure |

Recommended:
- **GPUs / loss leaders** → `competitive_floor` with 15–20% min margin
- **Accessories** (cooling, cables, thermal paste) → `margin_target` with 30–40% margin
- **Refurb / clearance** (future) → `match_cheapest`

---

## Quick start

```bash
# 1. Edit config/our_skus.yaml — set real COGS and current_price for each SKU
$EDITOR config/our_skus.yaml

# 2. Make sure Agent 1C has populated competitor prices for those SKUs
#    (this populates data/prices.db)
python -m agents.price_intelligence scan

# 3. Preview recommendations (no persistence — quick sanity check)
python -m agents.pricing_optimisation recommend

# 4. Propose: persist decisions to data/pricing.db and the audit log
python -m agents.pricing_optimisation propose

# 5. Review what's pending human approval (changes > 5%)
python -m agents.pricing_optimisation pending

# 6. Approve or reject
python -m agents.pricing_optimisation approve 4 --reviewer sam
python -m agents.pricing_optimisation reject  7 --reviewer sam --reason "hold price"

# 7. Export approved + auto-applied to Shopify CSV
python -m agents.pricing_optimisation export-csv --out data/shopify-prices.csv

# 8. Import in Shopify Admin → Products → Import → Choose file
```

---

## Hard guardrails (spec-compliant)

| Guardrail | Where enforced |
|-----------|----------------|
| Never below COGS | `OurSku.min_price` ≥ COGS by construction |
| Never below COGS+`min_margin_pct` | Strategy and agent-level clamp |
| Never above MSRP (if known) | Agent-level clamp |
| Change > `auto_apply_threshold_pct` requires human | `_classify_status()` → `pending_approval` |
| Auto-apply threshold default 5% | Matches spec: ">5% overnight change requires human" |
| Every action audited with `actor_type` | `AuditLog.append(actor_type=...)`; `decision_created` is agent, `decision_approved` is human |

The clamp logs `[GUARDRAIL: ...]` to the rationale so you can see when
a strategy was overridden:

```
Matched cheapest in-stock $90 @ A.
[GUARDRAIL: clamped UP to $125.00 margin floor (was $90)]
```

---

## CLI reference

```
python -m agents.pricing_optimisation \
    [--our-skus PATH]      # default: config/our_skus.yaml
    [--price-db PATH]      # default: data/prices.db (Agent 1C output)
    [--data-dir PATH]      # default: data/
    [--threshold PCT]      # auto-apply threshold; default 5.0
    [-v]                   # verbose
    <command>

Commands:
  recommend  [--sku S]              preview decisions, do NOT persist
  propose    [--sku S]              compute AND persist + audit
  pending                           list decisions awaiting approval
  approve    <id> [--reviewer N]    approve a pending decision (human action)
  reject     <id> [--reviewer N] [--reason MSG]
  export-csv [--out PATH] [--status S]  emit Shopify-compatible CSV
```

---

## Scheduling on the VPS

Agent 3 typically runs once a day, after the morning crawls have settled
and before the daily report goes out at 06:00. Drop into systemd:

```ini
# /etc/systemd/system/nh-pricing.service
[Unit]
Description=Neural Hardware — propose pricing decisions
Wants=network-online.target

[Service]
Type=oneshot
User=nh
WorkingDirectory=/home/nh/neuralhardware
ExecStart=/home/nh/neuralhardware/.venv/bin/python -m agents.pricing_optimisation propose

# /etc/systemd/system/nh-pricing.timer
[Timer]
OnCalendar=*-*-* 05:30:00 Australia/Sydney   # 30 min before the email
Persistent=true
Unit=nh-pricing.service
[Install]
WantedBy=timers.target
```

Then Agent 11 (06:00) picks up any new pending_approval decisions and
flags them in the daily report.

---

## Tests

```bash
python -m unittest tests.test_pricing -v
```

20 tests cover: SKU validation + min_price math, all three strategies,
floor-breach detection, MSRP cap, guardrail clamping, propose →
persist → audit, approve/reject workflows, CSV export.

---

## What's NOT here yet

- **Shopify Admin API integration** — currently emits a CSV the human
  imports. The wiring point is one new module: `agents.pricing_optimisation.shopify`.
- **Discovered-product mapping** — Agent 3 only handles SKUs declared
  in `our_skus.yaml`. If 1C's crawl mode found a product at competitor
  X that should map to our NH-RTX5090, you need to add the mapping
  manually (or add a `competitor_sku_map` field to OurSku — small change).
- **Price elasticity / demand forecasting** — spec mentions both; both
  require historical sales data we don't have yet.
- **Game theory** — spec mentions; this is `match_cheapest` with
  reaction modelling. Don't build until you have weeks of competitor
  response data to fit against.
- **Behavioural drift detection** — spec requires baseline + daily
  score; baseline needs ≥7 days of decisions. Add Agent 9 first.
