"""Tests for the Competitor Price Intelligence agent.

Run with:    python3 -m unittest tests.test_price_intelligence -v
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from agents.price_intelligence.anomaly import detect_anomaly
from agents.price_intelligence.audit import AuditLog
from agents.price_intelligence.extractor import ExtractionError, extract_price
from agents.price_intelligence.models import PricePoint, Sku
from agents.price_intelligence.storage import PriceStore


def make_sku(**overrides):
    defaults = dict(
        our_sku="NH-TEST",
        competitor="TestCo",
        product_name="Test Product",
        url="https://example.com/products/test",
        expected_price_min=Decimal("100"),
        expected_price_max=Decimal("10000"),
    )
    defaults.update(overrides)
    return Sku(**defaults)


JSONLD_HTML = """\
<!DOCTYPE html><html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "Test GPU",
  "offers": {
    "@type": "Offer",
    "price": "1499.00",
    "priceCurrency": "AUD",
    "availability": "https://schema.org/InStock"
  }
}
</script></head><body><h1>Test GPU</h1><span>$1,499.00</span></body></html>
"""

OPENGRAPH_HTML = """\
<!DOCTYPE html><html><head>
<meta property="product:price:amount" content="299.95">
<meta property="product:price:currency" content="AUD">
<meta property="product:availability" content="in stock">
</head><body><div>Some price text $299.95</div></body></html>
"""

SELECTOR_HTML = """\
<!DOCTYPE html><html><body>
<div class="page">
  <span class="product-price">$899.00</span>
</div></body></html>
"""

REGEX_HTML = """\
<!DOCTYPE html><html><body>
<p>Was $199, now $159.99 — save $40!</p>
</body></html>
"""

OUT_OF_RANGE_HTML = """\
<!DOCTYPE html><html><head>
<script type="application/ld+json">
{"@type":"Product","offers":{"@type":"Offer","price":"0.99","priceCurrency":"AUD"}}
</script></head></html>
"""

WRONG_CURRENCY_HTML = """\
<!DOCTYPE html><html><head>
<script type="application/ld+json">
{"@type":"Product","offers":{"@type":"Offer","price":"1499","priceCurrency":"USD"}}
</script></head></html>
"""


class ExtractorTests(unittest.TestCase):
    def test_jsonld_extraction(self):
        sku = make_sku()
        pt = extract_price(JSONLD_HTML, sku)
        self.assertEqual(pt.price, Decimal("1499.00"))
        self.assertEqual(pt.currency, "AUD")
        self.assertEqual(pt.extractor_method, "jsonld")
        self.assertGreaterEqual(pt.confidence, 0.9)
        self.assertTrue(pt.in_stock)

    def test_opengraph_extraction(self):
        sku = make_sku(expected_price_min=Decimal("10"))
        pt = extract_price(OPENGRAPH_HTML, sku)
        self.assertEqual(pt.price, Decimal("299.95"))
        self.assertEqual(pt.extractor_method, "opengraph")
        self.assertTrue(pt.in_stock)

    def test_selector_fallback(self):
        sku = make_sku(
            expected_price_min=Decimal("10"),
            selectors={"price": ".product-price"},
        )
        pt = extract_price(SELECTOR_HTML, sku)
        self.assertEqual(pt.price, Decimal("899.00"))
        self.assertEqual(pt.extractor_method, "selector")

    def test_regex_last_resort(self):
        sku = make_sku(expected_price_min=Decimal("10"))
        pt = extract_price(REGEX_HTML, sku)
        self.assertEqual(pt.extractor_method, "regex")
        self.assertEqual(pt.price, Decimal("159.99"))

    def test_rejects_price_below_min(self):
        sku = make_sku()
        with self.assertRaises(ExtractionError) as cm:
            extract_price(OUT_OF_RANGE_HTML, sku)
        self.assertIn("below expected min", str(cm.exception))

    def test_rejects_wrong_currency(self):
        sku = make_sku()
        with self.assertRaises(ExtractionError) as cm:
            extract_price(WRONG_CURRENCY_HTML, sku)
        msg = str(cm.exception)
        self.assertTrue(
            "USD" in msg and "AUD" in msg,
            f"expected currency mismatch error, got: {msg}",
        )

    def test_handles_dollar_signs_and_commas(self):
        html = """<script type="application/ld+json">
        {"@type":"Product","offers":{"@type":"Offer","price":"3,499.00","priceCurrency":"AUD"}}
        </script>"""
        sku = make_sku()
        pt = extract_price(html, sku)
        self.assertEqual(pt.price, Decimal("3499.00"))


class AnomalyTests(unittest.TestCase):
    def _history(self, prices: list[str], hours_ago_start: int = 30 * 24) -> list[PricePoint]:
        now = datetime.now(timezone.utc)
        out = []
        for i, p in enumerate(prices):
            out.append(
                PricePoint(
                    our_sku="NH-TEST",
                    competitor="TestCo",
                    url="https://example.com/x",
                    price=Decimal(p),
                    currency="AUD",
                    captured_at=now - timedelta(hours=hours_ago_start - i),
                    extractor_method="jsonld",
                    confidence=0.98,
                )
            )
        return out

    def test_no_anomaly_when_stable(self):
        history = self._history(["100", "101", "99", "100", "100", "101"])
        new = self._history(["100"], hours_ago_start=0)[0]
        self.assertIsNone(detect_anomaly(new, history))

    def test_rapid_change_flagged_high(self):
        history = self._history(["100", "100", "100"], hours_ago_start=24)
        # latest history point is 24h ago at price 100
        new = PricePoint(
            our_sku="NH-TEST",
            competitor="TestCo",
            url="https://example.com/x",
            price=Decimal("60"),
            currency="AUD",
            captured_at=datetime.now(timezone.utc),
            extractor_method="jsonld",
            confidence=0.98,
        )
        a = detect_anomaly(new, history)
        self.assertIsNotNone(a)
        self.assertEqual(a.severity, "high")

    def test_zscore_outlier_flagged(self):
        history = self._history(
            ["100", "101", "100", "99", "100", "101", "100"],
            hours_ago_start=30 * 24,
        )
        new = PricePoint(
            our_sku="NH-TEST",
            competitor="TestCo",
            url="https://example.com/x",
            price=Decimal("250"),
            currency="AUD",
            captured_at=datetime.now(timezone.utc),
            extractor_method="jsonld",
            confidence=0.98,
        )
        a = detect_anomaly(new, history)
        self.assertIsNotNone(a)
        self.assertIn("z-score", a.reason)


class StorageTests(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            store = PriceStore(Path(td) / "p.db")
            pt = PricePoint(
                our_sku="NH-TEST",
                competitor="TestCo",
                url="https://example.com/x",
                price=Decimal("199.99"),
                currency="AUD",
                extractor_method="jsonld",
                confidence=0.98,
            )
            store.record_point(pt)
            got = store.latest_point("NH-TEST", "TestCo")
            self.assertIsNotNone(got)
            self.assertEqual(got.price, Decimal("199.99"))
            self.assertEqual(got.competitor, "TestCo")


class AuditTests(unittest.TestCase):
    def test_hash_chain_intact(self):
        with tempfile.TemporaryDirectory() as td:
            log = AuditLog(Path(td) / "audit.jsonl")
            log.append(agent="t", action="a", params={"x": 1})
            log.append(agent="t", action="b", params={"x": 2})
            log.append(agent="t", action="c", params={"x": 3})
            ok, n, bad = log.verify()
            self.assertTrue(ok)
            self.assertEqual(n, 3)
            self.assertIsNone(bad)

    def test_tamper_detected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "audit.jsonl"
            log = AuditLog(path)
            log.append(agent="t", action="a", params={"x": 1})
            log.append(agent="t", action="b", params={"x": 2})
            lines = path.read_text().splitlines()
            # Tamper with the first entry's params after the fact
            import json as _json
            first = _json.loads(lines[0])
            first["params"]["x"] = 99
            lines[0] = _json.dumps(first, sort_keys=True)
            path.write_text("\n".join(lines) + "\n")
            ok, _, bad = log.verify()
            self.assertFalse(ok)
            self.assertIsNotNone(bad)


if __name__ == "__main__":
    unittest.main()
