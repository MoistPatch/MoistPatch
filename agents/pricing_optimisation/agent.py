from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

import yaml

from agents.price_intelligence.audit import AuditLog

from .models import CompetitorPrice, OurSku, PricingDecision
from .storage import DecisionStore
from .strategy import STRATEGIES


log = logging.getLogger(__name__)


class PricingOptimisationAgent:
    """Agent 3: Pricing & Margin Optimisation.

    Reads from Agent 1C's prices.db (read-only) and from a local
    our_skus.yaml describing our internal catalogue with COGS and
    margin constraints. Produces PricingDecisions which go through
    an approval workflow:

      - small changes (|Δ| ≤ auto_apply_threshold_pct) are auto-applied
      - larger changes are queued as pending_approval and need a
        human to run `approve <id>` or `reject <id> --reason ...`

    Guardrails (per spec):
      - never below COGS (enforced)
      - never below COGS+min_margin_pct floor (enforced)
      - never above MSRP if known (enforced)
      - >5% overnight change requires human approval (default threshold)
      - all decisions written to hash-chained audit log
    """

    AGENT_ID = "pricing-optimisation-3"
    DEFAULT_THRESHOLD_PCT = 5.0

    def __init__(
        self,
        *,
        our_skus_path: Path | str,
        price_db_path: Path | str,
        data_dir: Path | str = "data",
        auto_apply_threshold_pct: Optional[float] = None,
    ) -> None:
        self.our_skus_path = Path(our_skus_path)
        self.price_db_path = Path(price_db_path)
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.threshold_pct = (
            auto_apply_threshold_pct
            if auto_apply_threshold_pct is not None
            else self.DEFAULT_THRESHOLD_PCT
        )

        self.our_skus: dict[str, OurSku] = self._load_skus()
        self.decisions = DecisionStore(self.data_dir / "pricing.db")
        self.audit = AuditLog(self.data_dir / "pricing-audit.jsonl")

    def _load_skus(self) -> dict[str, OurSku]:
        if not self.our_skus_path.exists():
            raise FileNotFoundError(f"our_skus config not found: {self.our_skus_path}")
        with self.our_skus_path.open() as f:
            cfg = yaml.safe_load(f)
        out: dict[str, OurSku] = {}
        for entry in cfg.get("skus", []):
            sku = OurSku(**entry)
            if sku.our_sku in out:
                raise ValueError(f"duplicate our_sku in config: {sku.our_sku}")
            out[sku.our_sku] = sku
        return out

    # ------------------------------------------------------------ recommend

    def _fetch_competitor_prices(self, our_sku: str) -> list[CompetitorPrice]:
        """Read each competitor's MOST RECENT price for this SKU from 1C's DB."""
        if not self.price_db_path.exists():
            return []
        conn = sqlite3.connect(
            f"file:{self.price_db_path}?mode=ro", uri=True
        )
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """SELECT p.*
                   FROM price_points p
                   JOIN (
                       SELECT competitor, MAX(captured_at) AS latest
                       FROM price_points
                       WHERE our_sku = ?
                       GROUP BY competitor
                   ) latest ON latest.competitor = p.competitor
                            AND latest.latest = p.captured_at
                   WHERE p.our_sku = ?""",
                (our_sku, our_sku),
            ).fetchall()
        finally:
            conn.close()
        out = []
        for r in rows:
            out.append(
                CompetitorPrice(
                    competitor=r["competitor"],
                    price=Decimal(r["price"]),
                    in_stock=None if r["in_stock"] is None else bool(r["in_stock"]),
                    captured_at=datetime.fromisoformat(r["captured_at"]),
                    url=r["url"],
                    confidence=r["confidence"],
                )
            )
        return out

    def _classify_status(self, change_pct: float) -> str:
        if abs(change_pct) < 0.01:
            return "no_change"
        if abs(change_pct) <= self.threshold_pct:
            return "auto_applied"
        return "pending_approval"

    def _recommend_one(self, sku: OurSku) -> PricingDecision:
        competitors = self._fetch_competitor_prices(sku.our_sku)
        strat_fn = STRATEGIES.get(sku.strategy)
        if strat_fn is None:
            raise ValueError(f"unknown strategy: {sku.strategy!r}")

        if not competitors:
            # No data — flag for human attention
            return PricingDecision(
                our_sku=sku.our_sku,
                product_name=sku.product_name,
                current_price=sku.current_price,
                recommended_price=sku.current_price,
                cogs=sku.cogs,
                min_price=sku.min_price,
                change_amount=Decimal("0.00"),
                change_pct=0.0,
                new_margin_pct=sku.current_margin_pct,
                competitors_seen=0,
                strategy=sku.strategy,
                rationale=(
                    f"No competitor price points found for {sku.our_sku} in 1C's DB. "
                    f"Run `python -m agents.price_intelligence scan` (targeted) or "
                    f"add this SKU to competitors.yaml first."
                ),
                status="no_data",
                auto_apply_threshold_pct=self.threshold_pct,
            )

        recommended, rationale = strat_fn(sku, competitors)

        # Guardrail clamping (defence in depth — strategy should already respect these)
        clamped_reasons: list[str] = []
        if recommended < sku.min_price:
            clamped_reasons.append(
                f"clamped UP to ${sku.min_price} margin floor (was ${recommended})"
            )
            recommended = sku.min_price
        if sku.msrp is not None and recommended > sku.msrp:
            clamped_reasons.append(
                f"clamped DOWN to MSRP ${sku.msrp} (was ${recommended})"
            )
            recommended = sku.msrp
        if clamped_reasons:
            rationale = rationale + " [GUARDRAIL: " + "; ".join(clamped_reasons) + "]"

        change_amount = (recommended - sku.current_price).quantize(Decimal("0.01"))
        change_pct = (
            float(change_amount / sku.current_price * 100)
            if sku.current_price > 0
            else 0.0
        )
        new_margin_pct = (
            float((recommended - sku.cogs) / recommended * 100)
            if recommended > 0
            else 0.0
        )

        # Position our recommended price among in-stock competitors
        in_stock = sorted(
            [c for c in competitors if c.in_stock is not False],
            key=lambda c: c.price,
        )
        our_position = None
        if in_stock:
            our_position = sum(1 for c in in_stock if c.price < recommended) + 1
        cheapest = min(in_stock, key=lambda c: c.price) if in_stock else None

        return PricingDecision(
            our_sku=sku.our_sku,
            product_name=sku.product_name,
            current_price=sku.current_price,
            recommended_price=recommended,
            cogs=sku.cogs,
            min_price=sku.min_price,
            change_amount=change_amount,
            change_pct=change_pct,
            new_margin_pct=new_margin_pct,
            competitors_seen=len(competitors),
            cheapest_competitor=cheapest.competitor if cheapest else None,
            cheapest_in_stock_price=cheapest.price if cheapest else None,
            our_position=our_position,
            strategy=sku.strategy,
            rationale=rationale,
            status=self._classify_status(change_pct),
            auto_apply_threshold_pct=self.threshold_pct,
        )

    def recommend(
        self,
        sku_filter: Optional[list[str]] = None,
    ) -> list[PricingDecision]:
        """Compute (but do not persist) recommendations for every enabled SKU."""
        skus = [s for s in self.our_skus.values() if s.enabled]
        if sku_filter:
            wanted = {s.upper() for s in sku_filter}
            skus = [s for s in skus if s.our_sku in wanted]
        return [self._recommend_one(s) for s in skus]

    # ------------------------------------------------------------ propose

    def propose(
        self,
        sku_filter: Optional[list[str]] = None,
    ) -> list[PricingDecision]:
        """Compute recommendations AND persist them to the decisions table.

        Audits every decision. Auto-applied decisions can flow straight to
        the CSV export; pending_approval need `approve <id>` first.
        """
        decisions = self.recommend(sku_filter=sku_filter)
        self.audit.append(
            agent=self.AGENT_ID,
            action="propose_started",
            params={
                "sku_count": len(decisions),
                "threshold_pct": self.threshold_pct,
            },
        )
        for d in decisions:
            decision_id = self.decisions.record(d)
            self.audit.append(
                agent=self.AGENT_ID,
                action="decision_created",
                params={
                    "id": decision_id,
                    "our_sku": d.our_sku,
                    "current": str(d.current_price),
                    "recommended": str(d.recommended_price),
                    "change_pct": round(d.change_pct, 2),
                    "status": d.status,
                    "competitors_seen": d.competitors_seen,
                },
            )
        return decisions

    # ------------------------------------------------------------ approval flow

    def pending(self) -> list[dict]:
        return self.decisions.list_by_status("pending_approval")

    def approve(self, decision_id: int, *, reviewer: str = "human") -> bool:
        row = self.decisions.get(decision_id)
        if not row:
            return False
        if row["status"] != "pending_approval":
            log.warning(
                "decision %d is %r, not pending_approval", decision_id, row["status"]
            )
            return False
        ok = self.decisions.update_status(
            decision_id, "approved", reviewer=reviewer,
        )
        if ok:
            self.audit.append(
                agent=self.AGENT_ID,
                action="decision_approved",
                actor_type="human",
                params={"id": decision_id, "our_sku": row["our_sku"]},
                authorization=reviewer,
            )
        return ok

    def reject(
        self, decision_id: int, *, reviewer: str = "human", reason: str = "",
    ) -> bool:
        row = self.decisions.get(decision_id)
        if not row:
            return False
        if row["status"] != "pending_approval":
            return False
        ok = self.decisions.update_status(
            decision_id, "rejected", reviewer=reviewer, review_reason=reason,
        )
        if ok:
            self.audit.append(
                agent=self.AGENT_ID,
                action="decision_rejected",
                actor_type="human",
                params={
                    "id": decision_id, "our_sku": row["our_sku"], "reason": reason,
                },
                authorization=reviewer,
            )
        return ok

    # ------------------------------------------------------------ CSV export

    def export_shopify_csv(
        self,
        statuses: tuple[str, ...] = ("auto_applied", "approved"),
    ) -> list[tuple[str, Decimal]]:
        """Return [(sku, new_price), ...] for decisions with the given statuses.

        Caller formats as CSV. Shopify's bulk import expects:
            "Variant SKU","Variant Price"
        """
        out: list[tuple[str, Decimal]] = []
        seen: set[str] = set()
        for status in statuses:
            for row in self.decisions.list_by_status(status, limit=10_000):
                if row["our_sku"] in seen:
                    continue
                seen.add(row["our_sku"])
                out.append((row["our_sku"], Decimal(row["recommended_price"])))
        return out
