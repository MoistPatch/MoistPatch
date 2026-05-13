from __future__ import annotations

import argparse
import csv
import logging
import sys
from decimal import Decimal
from pathlib import Path
from typing import Optional

from .agent import PricingOptimisationAgent


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _agent(args: argparse.Namespace) -> PricingOptimisationAgent:
    return PricingOptimisationAgent(
        our_skus_path=Path(args.our_skus),
        price_db_path=Path(args.price_db),
        data_dir=Path(args.data_dir),
        auto_apply_threshold_pct=args.threshold,
    )


def _arrow(pct: float) -> str:
    if pct < -0.01:
        return "↓"
    if pct > 0.01:
        return "↑"
    return "·"


def _format_decision(d) -> str:
    return (
        f"  [{d.status:18}] {d.our_sku:18}  "
        f"${d.current_price:>9} → ${d.recommended_price:>9}  "
        f"{_arrow(d.change_pct)}{abs(d.change_pct):>5.2f}%  "
        f"margin {d.new_margin_pct:>5.1f}%  "
        f"({d.competitors_seen} comps)"
    )


def cmd_recommend(args: argparse.Namespace) -> int:
    agent = _agent(args)
    decisions = agent.recommend(sku_filter=args.sku or None)
    if not decisions:
        print("no SKUs to evaluate (check our_skus.yaml + --sku filter)")
        return 1
    print("Pricing recommendations (preview — not persisted):")
    print()
    for d in decisions:
        print(_format_decision(d))
        if args.verbose:
            print(f"      rationale: {d.rationale}")
    counts: dict[str, int] = {}
    for d in decisions:
        counts[d.status] = counts.get(d.status, 0) + 1
    print()
    print("  Summary: " + " · ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    return 0


def cmd_propose(args: argparse.Namespace) -> int:
    agent = _agent(args)
    decisions = agent.propose(sku_filter=args.sku or None)
    print(f"Proposed {len(decisions)} decisions and persisted to pricing.db.")
    print()
    for d in decisions:
        print(_format_decision(d))
    print()
    print(
        f"Run `python -m agents.pricing_optimisation pending` to see decisions "
        f"awaiting human approval (changes > {agent.threshold_pct:.1f}%)."
    )
    return 0


def cmd_pending(args: argparse.Namespace) -> int:
    agent = _agent(args)
    rows = agent.pending()
    if not rows:
        print("no decisions awaiting approval.")
        return 0
    print(f"Decisions awaiting human approval ({len(rows)}):\n")
    for r in rows:
        print(f"  #{r['id']:>4}  {r['our_sku']:18}  "
              f"${float(r['current_price']):>9.2f} → ${float(r['recommended_price']):>9.2f}  "
              f"({r['change_pct']:+.2f}%)  {r['strategy']}")
        print(f"          {r['rationale']}")
        print()
    print("Approve with:  python -m agents.pricing_optimisation approve <id>")
    print("Reject with:   python -m agents.pricing_optimisation reject  <id> --reason '...'")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    agent = _agent(args)
    ok = agent.approve(args.id, reviewer=args.reviewer)
    if ok:
        print(f"✓ decision #{args.id} approved by {args.reviewer}.")
        return 0
    print(f"✗ could not approve #{args.id} (not pending? doesn't exist?)", file=sys.stderr)
    return 1


def cmd_reject(args: argparse.Namespace) -> int:
    agent = _agent(args)
    ok = agent.reject(args.id, reviewer=args.reviewer, reason=args.reason)
    if ok:
        print(f"✓ decision #{args.id} rejected by {args.reviewer}: {args.reason}")
        return 0
    print(f"✗ could not reject #{args.id}", file=sys.stderr)
    return 1


def cmd_export_csv(args: argparse.Namespace) -> int:
    agent = _agent(args)
    rows = agent.export_shopify_csv(
        statuses=tuple(args.status or ["auto_applied", "approved"])
    )
    if not rows:
        print("no decisions to export (check --status filter).", file=sys.stderr)
        return 1
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Variant SKU", "Variant Price"])
        for sku, price in rows:
            w.writerow([sku, f"{price:.2f}"])
    print(f"✓ wrote {len(rows)} rows to {target}")
    print("  Import into Shopify: Admin → Products → Import → Choose file.")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agents.pricing_optimisation",
        description="Agent 3 — Pricing & Margin Optimisation",
    )
    parser.add_argument("--our-skus", default="config/our_skus.yaml",
                        help="our internal SKU catalogue")
    parser.add_argument("--price-db", default="data/prices.db",
                        help="Agent 1C's price database (read-only)")
    parser.add_argument("--data-dir", default="data",
                        help="where to store pricing.db and audit log")
    parser.add_argument("--threshold", type=float, default=None,
                        help="auto-apply threshold percent (default 5%)")
    parser.add_argument("-v", "--verbose", action="store_true")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("recommend", help="preview recommendations (do not persist)")
    p_rec.add_argument("--sku", action="append", help="filter to specific SKU(s)")
    p_rec.set_defaults(func=cmd_recommend)

    p_prop = sub.add_parser("propose", help="compute and PERSIST recommendations")
    p_prop.add_argument("--sku", action="append")
    p_prop.set_defaults(func=cmd_propose)

    p_pend = sub.add_parser("pending", help="show decisions awaiting human approval")
    p_pend.set_defaults(func=cmd_pending)

    p_app = sub.add_parser("approve", help="approve a pending decision")
    p_app.add_argument("id", type=int)
    p_app.add_argument("--reviewer", default="human")
    p_app.set_defaults(func=cmd_approve)

    p_rej = sub.add_parser("reject", help="reject a pending decision")
    p_rej.add_argument("id", type=int)
    p_rej.add_argument("--reviewer", default="human")
    p_rej.add_argument("--reason", default="not specified")
    p_rej.set_defaults(func=cmd_reject)

    p_csv = sub.add_parser("export-csv", help="export approved decisions as Shopify CSV")
    p_csv.add_argument("--out", default="data/shopify-prices.csv")
    p_csv.add_argument("--status", action="append",
                       help="statuses to include (default: auto_applied + approved)")
    p_csv.set_defaults(func=cmd_export_csv)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
