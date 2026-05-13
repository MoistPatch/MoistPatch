"""Tests for Agent 3 (Pricing Optimisation).

Run with: python3 -m unittest tests.test_pricing -v
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import yaml

from agents.price_intelligence.models import PricePoint
from agents.price_intelligence.storage import PriceStore
from agents.pricing_optimisation.agent import PricingOptimisationAgent
from agents.pricing_optimisation.models import CompetitorPrice, OurSku, PricingDecision
from agents.pricing_optimisation.strategy import (
    STRATEGIES,
    competitive_floor,
    margin_target,
    match_cheapest,
)


# ---------------------------------------------------------------- helpers

def _sku(**overrides) -> OurSku:
    defaults = dict(
        our_sku="NH-TEST",
        product_name="Test Product",
        cogs="100.00",
        msrp="200.00",
        current_price="150.00",
        min_margin_pct=20.0,
        strategy="competitive_floor",
    )
    defaults.update(overrides)
    return OurSku(**defaults)


def _comp(price: str, *, name: str = "TestCo", in_stock: bool | None = True) -> CompetitorPrice:
    return CompetitorPrice(
        competitor=name,
        price=Decimal(price),
        in_stock=in_stock,
        captured_at=datetime.now(timezone.utc),
        url="https://example.com/x",
    )


def _seed_price_db(db_path: Path, rows: list[tuple]) -> None:
    """rows: [(our_sku, competitor, price_str, in_stock_bool), ...]"""
    store = PriceStore(db_path)
    now = datetime.now(timezone.utc)
    for our_sku, comp, price, in_stock in rows:
        store.record_point(
            PricePoint(
                our_sku=our_sku, competitor=comp,
                url=f"https://demo/{comp.lower()}",
                price=Decimal(price), currency="AUD",
                in_stock=in_stock, captured_at=now,
                extractor_method="jsonld", confidence=0.98,
            )
        )


def _write_our_skus(tmp: Path, entries: list[dict]) -> Path:
    p = tmp / "our_skus.yaml"
    p.write_text(yaml.safe_dump({"skus": entries}))
    return p


# ---------------------------------------------------------------- OurSku

class OurSkuTests(unittest.TestCase):
    def test_min_price_computed(self):
        s = _sku(cogs="100", min_margin_pct=20)
        # floor = 100 / 0.80 = 125
        self.assertEqual(s.min_price, Decimal("125.00"))

    def test_current_margin(self):
        s = _sku(cogs="100", current_price="150")
        # margin = (150 - 100) / 150 = 33.33%
        self.assertAlmostEqual(s.current_margin_pct, 33.33, places=1)

    def test_sku_uppercased(self):
        s = _sku(our_sku="nh-test-2")
        self.assertEqual(s.our_sku, "NH-TEST-2")

    def test_invalid_sku_rejected(self):
        with self.assertRaises(Exception):
            _sku(our_sku="bad sku!")


# ---------------------------------------------------------------- strategies

class CompetitiveFloorTests(unittest.TestCase):
    def test_no_competitors(self):
        sku = _sku()
        price, why = competitive_floor(sku, [])
        self.assertEqual(price, sku.current_price)
        self.assertIn("No competitor data", why)

    def test_all_out_of_stock(self):
        sku = _sku()
        comps = [_comp("90", in_stock=False), _comp("100", name="X", in_stock=False)]
        price, why = competitive_floor(sku, comps)
        self.assertEqual(price, sku.current_price)
        self.assertIn("out of stock", why.lower())

    def test_matches_cheapest_in_stock(self):
        sku = _sku(cogs="100", current_price="150", min_margin_pct=20)
        # cheapest in-stock = 140 (above floor of 125)
        comps = [_comp("140", name="A"), _comp("145", name="B"), _comp("90", name="C", in_stock=False)]
        price, why = competitive_floor(sku, comps)
        self.assertEqual(price, Decimal("140"))
        self.assertIn("Matched cheapest in-stock", why)

    def test_holds_floor_when_competitor_too_cheap(self):
        sku = _sku(cogs="100", current_price="150", min_margin_pct=20)
        # cheapest = 110 (below floor of 125)
        comps = [_comp("110", name="A"), _comp("120", name="B")]
        price, why = competitive_floor(sku, comps)
        self.assertEqual(price, Decimal("125.00"))
        self.assertIn("margin floor", why)

    def test_caps_at_msrp(self):
        sku = _sku(cogs="100", current_price="150", min_margin_pct=20, msrp="180")
        comps = [_comp("200", name="A")]  # above MSRP
        price, why = competitive_floor(sku, comps)
        self.assertEqual(price, Decimal("180.00"))
        self.assertIn("MSRP", why)


class MarginTargetTests(unittest.TestCase):
    def test_holds_target_margin(self):
        sku = _sku(cogs="100", current_price="150", min_margin_pct=20)
        # target 30%: price = 100 / 0.70 = 142.86
        price, why = margin_target(sku, [_comp("80"), _comp("90")], target_margin_pct=30)
        self.assertEqual(price, Decimal("142.86"))
        self.assertIn("Margin-anchored", why)

    def test_respects_floor(self):
        sku = _sku(cogs="100", current_price="150", min_margin_pct=40)
        # target 30% (price 142.86) is BELOW floor (166.67); floor wins
        price, _ = margin_target(sku, [_comp("80")], target_margin_pct=30)
        self.assertEqual(price, sku.min_price)


class MatchCheapestTests(unittest.TestCase):
    def test_matches_even_below_floor(self):
        # match_cheapest is intentionally allowed to breach floor;
        # guardrails in the agent clamp it.
        sku = _sku(cogs="100", min_margin_pct=20)  # floor 125
        comps = [_comp("90"), _comp("100")]
        price, _ = match_cheapest(sku, comps)
        self.assertEqual(price, Decimal("90"))


# ---------------------------------------------------------------- agent

class AgentTests(unittest.TestCase):

    def _build_agent(self, tmp: Path, *, our_skus: list[dict], price_rows: list[tuple],
                    threshold: float = 5.0) -> PricingOptimisationAgent:
        our_path = _write_our_skus(tmp, our_skus)
        price_db = tmp / "prices.db"
        _seed_price_db(price_db, price_rows)
        return PricingOptimisationAgent(
            our_skus_path=our_path,
            price_db_path=price_db,
            data_dir=tmp / "agent3-data",
            auto_apply_threshold_pct=threshold,
        )

    def test_no_competitor_data_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            agent = self._build_agent(
                tmp,
                our_skus=[{
                    "our_sku": "NH-X", "product_name": "X", "cogs": 100,
                    "current_price": 150, "min_margin_pct": 20,
                }],
                price_rows=[],
            )
            recs = agent.recommend()
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0].status, "no_data")
            self.assertIn("No competitor", recs[0].rationale)

    def test_small_change_auto_applied(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            agent = self._build_agent(
                tmp,
                our_skus=[{
                    "our_sku": "NH-X", "product_name": "X", "cogs": 100,
                    "current_price": 150, "min_margin_pct": 20,
                }],
                # cheapest in-stock 147 vs current 150 = -2% change
                price_rows=[("NH-X", "A", "147.00", True), ("NH-X", "B", "150", True)],
            )
            recs = agent.recommend()
            self.assertEqual(recs[0].status, "auto_applied")
            self.assertEqual(recs[0].recommended_price, Decimal("147.00"))

    def test_large_change_pending_approval(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            agent = self._build_agent(
                tmp,
                our_skus=[{
                    "our_sku": "NH-X", "product_name": "X", "cogs": 100,
                    "current_price": 150, "min_margin_pct": 20,
                }],
                # cheapest 130 vs 150 = -13.3% (above 5% threshold)
                price_rows=[("NH-X", "A", "130", True)],
            )
            recs = agent.recommend()
            self.assertEqual(recs[0].status, "pending_approval")
            self.assertEqual(recs[0].recommended_price, Decimal("130"))

    def test_propose_persists_and_audits(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            agent = self._build_agent(
                tmp,
                our_skus=[{
                    "our_sku": "NH-X", "product_name": "X", "cogs": 100,
                    "current_price": 150, "min_margin_pct": 20,
                }],
                price_rows=[("NH-X", "A", "130", True)],
            )
            agent.propose()
            pending = agent.pending()
            self.assertEqual(len(pending), 1)
            # audit chain intact
            ok, n, bad = agent.audit.verify()
            self.assertTrue(ok)
            self.assertGreaterEqual(n, 2)  # propose_started + decision_created

    def test_approve_workflow(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            agent = self._build_agent(
                tmp,
                our_skus=[{
                    "our_sku": "NH-X", "product_name": "X", "cogs": 100,
                    "current_price": 150, "min_margin_pct": 20,
                }],
                price_rows=[("NH-X", "A", "130", True)],
            )
            agent.propose()
            pending = agent.pending()
            decision_id = pending[0]["id"]
            ok = agent.approve(decision_id, reviewer="sam")
            self.assertTrue(ok)
            self.assertEqual(len(agent.pending()), 0)
            # Re-approving should fail
            self.assertFalse(agent.approve(decision_id))

    def test_reject_workflow(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            agent = self._build_agent(
                tmp,
                our_skus=[{
                    "our_sku": "NH-X", "product_name": "X", "cogs": 100,
                    "current_price": 150, "min_margin_pct": 20,
                }],
                price_rows=[("NH-X", "A", "130", True)],
            )
            agent.propose()
            decision_id = agent.pending()[0]["id"]
            self.assertTrue(agent.reject(decision_id, reviewer="sam", reason="held floor"))
            self.assertEqual(len(agent.pending()), 0)

    def test_guardrail_clamps_below_floor_recommendations(self):
        """If a strategy returns below the floor, the agent clamps it up."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            agent = self._build_agent(
                tmp,
                our_skus=[{
                    "our_sku": "NH-X", "product_name": "X", "cogs": 100,
                    "current_price": 150, "min_margin_pct": 20,
                    "strategy": "match_cheapest",  # this one ignores the floor
                }],
                # cheapest 90 — below floor of 125
                price_rows=[("NH-X", "A", "90", True)],
            )
            recs = agent.recommend()
            # Guardrail should clamp to floor
            self.assertEqual(recs[0].recommended_price, Decimal("125.00"))
            self.assertIn("GUARDRAIL", recs[0].rationale)

    def test_csv_export_contains_approved_and_auto_applied(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            agent = self._build_agent(
                tmp,
                our_skus=[
                    {"our_sku": "NH-A", "product_name": "A", "cogs": 100,
                     "current_price": 150, "min_margin_pct": 20},
                    {"our_sku": "NH-B", "product_name": "B", "cogs": 100,
                     "current_price": 150, "min_margin_pct": 20},
                ],
                # A: -2% (auto_applied), B: -13% (pending → we'll approve)
                price_rows=[
                    ("NH-A", "X", "147", True),
                    ("NH-B", "Y", "130", True),
                ],
            )
            agent.propose()
            pending = agent.pending()
            for row in pending:
                agent.approve(row["id"], reviewer="sam")
            rows = agent.export_shopify_csv()
            skus = {sku: price for sku, price in rows}
            self.assertEqual(skus["NH-A"], Decimal("147.00"))
            self.assertEqual(skus["NH-B"], Decimal("130.00"))


if __name__ == "__main__":
    unittest.main()
