# Pricing Agent — Backlog

> Living document. Update as work moves through.
> Canonical retailer catalogue: `config/au_retailers.yaml` (47 retailers across 6 tiers).
> Currently active in `config/competitors.yaml`: 19 Tier 2 specialists.

---

## 🟢 Active (Tier 2 — wired, awaiting first run)

All 19 specialist PC retailers are configured. Before relying on any of
them, run a small test crawl to verify the sitemap URL and product URL
patterns are correct, then tune as needed.

```bash
# Test each retailer with a tiny budget, in priority order
python -m agents.price_intelligence crawl "Centre Com"   --limit 5
python -m agents.price_intelligence crawl "PLE Computers" --limit 5
python -m agents.price_intelligence crawl "Scorptec"      --limit 5
python -m agents.price_intelligence crawl "Mwave"         --limit 5
python -m agents.price_intelligence crawl "Umart"         --limit 5
python -m agents.price_intelligence crawl "MSY Technology" --limit 5
python -m agents.price_intelligence crawl "PC Case Gear"  --limit 5
python -m agents.price_intelligence crawl "Computer Alliance" --limit 5
python -m agents.price_intelligence crawl "MegaBuy"       --limit 5
python -m agents.price_intelligence crawl "CPL Online"    --limit 5
# ... etc
```

For each retailer, record one of three outcomes:

| Outcome | What it means | Action |
|---|---|---|
| ✅ products priced | sitemap + JSON-LD work | scale up `--limit` |
| 🟡 0 products, "no schema" skips | sitemap works, but pages lack JSON-LD | needs Playwright + custom selectors |
| ❌ scrape failures (4xx/5xx) | Cloudflare or anti-bot blocking | needs Playwright + TLS fingerprint or proxy |

Track findings in `data/audit.jsonl` and `scrape_failures` table.

### Tunings to confirm per retailer

- [ ] `product_url_patterns` actually match real product URLs
- [ ] `sitemap_url` exists (or robots.txt declares it)
- [ ] `crawl_price_max` covers their high-end SKUs (e.g. workstations $20k+)
- [ ] Stock-status JSON-LD `availability` field is populated

---

## 🟡 Pending — Tier 1 (Major national retailers)

Not in active config. Likely need Playwright due to JS-rendered pricing
or anti-bot. Lower priority because catalogue is broader than just
computing.

- [ ] **JB Hi-Fi** (`jbhifi.com.au`) — broad consumer electronics, computing range
- [ ] **Officeworks** (`officeworks.com.au`) — competitive laptop/peripheral pricing
- [ ] **Harvey Norman** (`harveynorman.com.au`) — franchise-based, may have anti-bot
- [ ] **The Good Guys** (`thegoodguys.com.au`) — JB subsidiary, similar catalogue
- [ ] **Amazon Australia** (`amazon.com.au`) — anti-bot heavy; consider Product Advertising API instead

---

## 🟡 Pending — Tier 3 (Electronics / mixed retail)

Useful for monitors, NAS, networking, peripherals (not core components).

- [ ] **digiDirect** (`digidirect.com.au`)
- [ ] **Device Deal** (`devicedeal.com.au`) — NAS/networking specialist (QNAP, Synology)
- [ ] **Kogan** (`kogan.com.au`) — budget tier
- [ ] **Bing Lee** (`binglee.com.au`) — NSW/ACT focused
- [ ] **Dick Smith** (`dicksmith.com.au`) — Kogan-owned, online only

---

## 🟡 Pending — Tier 4 (Manufacturer direct — MSRP cross-reference)

Lower priority. Use to detect MSRP-vs-reseller spreads. Often Cloudflare
or aggressive anti-bot.

- [ ] **ASUS Australia** (`asus.com/au`)
- [ ] **MSI Australia** (`au.msi.com`)
- [ ] **Gigabyte Australia** (`gigabyte.com/au`)
- [ ] **NVIDIA GeForce** (`nvidia.com/en-au/shop`) — FE cards, limited
- [ ] **AMD Australia** (`amd.com/en/direct-buy/au`)
- [ ] **Intel** (`intel.com.au/.../shop`)
- [ ] **Dell Australia** (`dell.com/en-au`)
- [ ] **HP Australia** (`hp.com/au-en/shop`)
- [ ] **Lenovo Australia** (`lenovo.com/au/en/shop`)
- [ ] **Apple Australia** (`apple.com/au/shop`)

---

## 🟡 Pending — Tier 5 (Refurbished/secondary — exclude from new-price comparisons)

Track separately so reports don't conflate refurb prices with new.
Requires a `condition: new|refurb|used` column on `price_points` first.

- [ ] **Australian Computer Traders** (`australiancomputertraders.com.au`)
- [ ] **EMPR Australia** (`store.emprgroup.com.au`) — parts only, exclude from new pricing
- [ ] **PC Hardware Refresh** (`pchardwarerefresh.com.au`)
- [ ] **eBay AU computing category** — discount unless verified storefront

---

## 🔵 Pending — Tier 6 (Aggregator adapters — high leverage)

This is the **biggest force multiplier in the entire pricing agent**.
A working StaticICE adapter would give us competitor coverage for thousands
of SKUs without crawling each retailer individually.

- [ ] **StaticICE adapter** (`staticice.com.au`) — most comprehensive AU
      PC-hardware price index. Per-SKU query API; returns prices across
      every retailer they index, including small/regional vendors we
      don't have in `competitors.yaml`. **Top priority.**
- [ ] **PriceSpy adapter** (`pricespy.com.au`) — useful historical
      depth (graphs); supplements our own price_history.
- [ ] **Google Shopping AU** (`shopping.google.com.au`) — broad but
      anti-bot heavy. Consider Merchant Center API instead.
- [ ] **GetPrice adapter** (`getprice.com.au`)
- [ ] **ShopBot adapter** (`shopbot.com.au`)
- [ ] **MyShopping adapter** (`myshopping.com.au`)

Aggregator adapters need a different interface than the existing crawler.
They take a search query (SKU/product name) and return a list of
(retailer, price, in_stock, url) tuples. Treat them as a new agent
subtype: `agents.price_intelligence.aggregator`.

---

## 🟣 Platform / infrastructure

- [ ] **Playwright renderer** — wire `renderer: playwright` field in
      competitor config to a Playwright-driven scrape path. Required
      for any retailer that gates JSON-LD behind JS or has Cloudflare.
- [ ] **Proxy rotation** — residential proxy pool for retailers that
      block datacentre IPs. Pluggable via env var.
- [ ] **`condition` column** on `price_points` — `new | refurb | used`
      so Tier 5 retailers can be ingested without polluting new-product
      comparisons.
- [ ] **Frontier persistence** — resume an interrupted crawl from where
      it left off (currently `crawl` re-fetches sitemap each run).
- [ ] **Per-host concurrency** — currently one URL at a time per
      competitor. Could safely parallelise within rate-limit budget.
- [ ] **Delta detection** — flag retailers that suddenly stop publishing
      a product (likely discontinued or out of stock long-term).

---

## 🟣 Reporting integration

- [ ] **Agent 11 grouping by tier** — daily report shows Tier 2 in a
      "competitors" block and Tier 4 in a "MSRP" block separately.
- [ ] **Per-SKU spread alert** — when our price is more than X% above
      cheapest competitor, flag in the daily report's anomalies section.
- [ ] **Coverage report** — for each of our active SKUs (NH-*), how
      many competitors do we have a recent price for?

---

## 🟣 Operational gotchas captured from the source document

- **Mwave** is under **DigiDirect Group** since June 2025. Pricing data
  is still valid; **stock availability is less reliable** post-acquisition
  due to slow fulfilment reports. Don't use Mwave's `in_stock` field
  alone to drive our own stock decisions.
- **Manufacturer-direct prices** (Tier 4) are usually higher than
  authorised resellers. Don't treat them as "cheapest" candidates;
  treat them as MSRP signal.
- **EMPR and Australian Computer Traders** are parts/refurb only.
  Exclude from new-hardware competitive analysis.
- **eBay AU** is secondary market. Only use prices from verified
  retailer storefronts, not individual sellers.

---

## How to promote a retailer from catalogue → active

1. Open `config/au_retailers.yaml`, find the entry, copy its `name`
   and `url`.
2. Add an entry to `config/competitors.yaml` under `competitors:` with:
   - `sitemap_url: <best guess from /sitemap.xml>`
   - `product_url_patterns: ["*/product/*", "*/products/*"]` (then refine)
   - `enabled: true`
3. Flip `active: true` in `au_retailers.yaml` for that retailer.
4. Test: `python -m agents.price_intelligence crawl "<Name>" --limit 5`
5. Inspect failures: `sqlite3 data/prices.db 'SELECT * FROM scrape_failures'`
6. Tune patterns; rerun. Once stable, scale `--limit` or set
   `crawl_max_products` per-competitor.
