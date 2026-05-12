"""Tests for Agent 11 (Reporting).

Run with: python3 -m unittest tests.test_reporting -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from agents.price_intelligence.models import PricePoint
from agents.price_intelligence.storage import PriceStore
from agents.reporting.agent import ReportingAgent
from agents.reporting.compiler import DailyReport, ReportCompiler
from agents.reporting.sender import SmtpConfig, build_message


def _seed(db: Path) -> None:
    store = PriceStore(db)
    now = datetime.now(timezone.utc)
    rows = [
        ("NH-RTX5090", "Centre Com", Decimal("3499.00"), True, "jsonld", 0.98),
        ("NH-RTX5090", "Mwave", Decimal("3399.00"), True, "opengraph", 0.92),
        ("NH-RTX5090", "Scorptec", Decimal("3549.00"), False, "jsonld", 0.98),
    ]
    for sku, comp, price, in_stock, method, conf in rows:
        store.record_point(
            PricePoint(
                our_sku=sku,
                competitor=comp,
                url=f"https://demo.example.com/{comp}",
                price=price,
                currency="AUD",
                in_stock=in_stock,
                captured_at=now,
                extractor_method=method,
                confidence=conf,
            )
        )


class CompilerTests(unittest.TestCase):
    def test_compile_returns_comparison(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "prices.db"
            _seed(db)
            report = ReportCompiler(db).compile(hours=24)
            self.assertEqual(report.skus_tracked, 1)
            self.assertEqual(report.competitors_tracked, 3)
            self.assertEqual(report.scans_succeeded, 3)
            self.assertEqual(len(report.comparisons), 1)
            cmp = report.comparisons[0]
            self.assertEqual(cmp.our_sku, "NH-RTX5090")
            self.assertEqual(len(cmp.prices), 3)
            self.assertEqual(cmp.cheapest.competitor, "Mwave")
            self.assertEqual(cmp.cheapest.price, Decimal("3399.00"))

    def test_cheapest_skips_out_of_stock(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "prices.db"
            store = PriceStore(db)
            now = datetime.now(timezone.utc)
            # cheapest is OUT of stock, second-cheapest in stock
            store.record_point(PricePoint(
                our_sku="X", competitor="A", url="https://demo/a",
                price=Decimal("100"), currency="AUD", in_stock=False,
                captured_at=now, extractor_method="jsonld", confidence=0.98,
            ))
            store.record_point(PricePoint(
                our_sku="X", competitor="B", url="https://demo/b",
                price=Decimal("110"), currency="AUD", in_stock=True,
                captured_at=now, extractor_method="jsonld", confidence=0.98,
            ))
            report = ReportCompiler(db).compile(hours=24)
            cmp = report.comparisons[0]
            self.assertEqual(cmp.cheapest.competitor, "B")

    def test_missing_db_raises(self):
        with self.assertRaises(FileNotFoundError):
            ReportCompiler("/tmp/does-not-exist.db").compile()


class HallucinationRiskTests(unittest.TestCase):
    def _report(self, conf: float) -> DailyReport:
        now = datetime.now(timezone.utc)
        return DailyReport(period_start=now, period_end=now, avg_confidence=conf)

    def test_risk_bands(self):
        self.assertEqual(self._report(0.98).hallucination_risk, "very low")
        self.assertEqual(self._report(0.90).hallucination_risk, "low")
        self.assertEqual(self._report(0.75).hallucination_risk, "moderate")
        self.assertEqual(self._report(0.60).hallucination_risk, "elevated")
        self.assertEqual(self._report(0.40).hallucination_risk, "high")


class RenderTests(unittest.TestCase):
    def test_html_contains_competitor_prices(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "prices.db"
            _seed(db)
            agent = ReportingAgent(db)
            report = agent.build_report(hours=24)
            subject, html, text = agent.render(report)
            self.assertIn("Neural Hardware", html)
            self.assertIn("NH-RTX5090", html)
            self.assertIn("Centre Com", html)
            self.assertIn("Mwave", html)
            self.assertIn("3399", html)
            self.assertIn("NH-RTX5090", text)
            self.assertIn("Mwave", text)

    def test_demo_report_shows_banner(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "prices.db"
            _seed(db)
            agent = ReportingAgent(db)
            report = agent.build_report(hours=24, is_demo=True)
            subject, html, text = agent.render(report)
            self.assertIn("DEMO", subject)
            self.assertIn("DEMO", html)
            self.assertIn("DEMO", text)


class SenderTests(unittest.TestCase):
    def test_smtp_config_from_env_missing(self):
        # Stash and clear
        saved = {k: os.environ.pop(k, None) for k in ("SMTP_USER", "SMTP_PASS")}
        try:
            with self.assertRaises(RuntimeError) as cm:
                SmtpConfig.from_env()
            self.assertIn("SMTP", str(cm.exception))
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_smtp_config_from_env_ok(self):
        os.environ["SMTP_USER"] = "bot@example.com"
        os.environ["SMTP_PASS"] = "abcdabcdabcdabcd"
        try:
            cfg = SmtpConfig.from_env()
            self.assertEqual(cfg.user, "bot@example.com")
            self.assertEqual(cfg.host, "smtp.gmail.com")
            self.assertEqual(cfg.port, 587)
            self.assertTrue(cfg.use_starttls)
        finally:
            del os.environ["SMTP_USER"], os.environ["SMTP_PASS"]

    def test_build_message_has_html_and_text(self):
        cfg = SmtpConfig(
            host="smtp.gmail.com", port=587,
            user="bot@example.com", password="x",
            from_name="Agent 11", from_addr="bot@example.com",
        )
        msg = build_message(
            config=cfg, to="sam@example.com", subject="test",
            html_body="<p>hi</p>", text_body="hi", bcc="audit@example.com",
        )
        self.assertEqual(msg["To"], "sam@example.com")
        self.assertEqual(msg["Bcc"], "audit@example.com")
        self.assertEqual(msg["X-Agent"], "neural-hardware/price-reporter-11")
        # multipart/alternative with text and html
        parts = list(msg.walk())
        types = [p.get_content_type() for p in parts]
        self.assertIn("text/plain", types)
        self.assertIn("text/html", types)


class SafetyTests(unittest.TestCase):
    def test_refuses_to_send_demo_without_force(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "prices.db"
            _seed(db)
            agent = ReportingAgent(db)
            report = agent.build_report(hours=24, is_demo=True)
            with self.assertRaises(RuntimeError) as cm:
                agent.send_report(report, to="sam@example.com")
            self.assertIn("DEMO", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
