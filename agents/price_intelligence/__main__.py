from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from .agent import PriceIntelligenceAgent


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_scan(agent: PriceIntelligenceAgent) -> int:
    report = asyncio.run(agent.scan_all())
    print()
    print("=" * 70)
    print(f"  {report.summary()}")
    print("=" * 70)
    if report.changes:
        print("\nPRICE CHANGES:")
        for c in report.changes:
            arrow = "↑" if c.change_amount > 0 else "↓"
            print(
                f"  {arrow} {c.our_sku:18} @ {c.competitor:14} "
                f"${c.old_price} → ${c.new_price} ({c.change_percent:+.1f}%)"
            )
    if report.anomalies:
        print("\nANOMALIES:")
        for a in report.anomalies:
            print(f"  [{a.severity.upper():6}] {a.our_sku:18} @ {a.competitor:14} ${a.price}")
            print(f"           → {a.reason}")
    if report.errors:
        print("\nFAILURES:")
        for sku, comp, err in report.errors:
            print(f"  ✗ {sku:18} @ {comp:14} {err}")
    return 0 if report.failed == 0 else 1


def cmd_list(agent: PriceIntelligenceAgent) -> int:
    print("COMPETITORS:")
    for c in agent.list_competitors():
        flag = " " if c.enabled else "✗"
        print(f"  [{flag}] {c.name:20} {c.domain:30} ({c.renderer})")
    print("\nTRACKED SKUs:")
    for s in agent.list_skus():
        flag = " " if s.enabled else "✗"
        print(f"  [{flag}] {s.our_sku:18} @ {s.competitor:14} {s.product_name}")
    return 0


def cmd_history(
    agent: PriceIntelligenceAgent, our_sku: str, competitor: str, days: int
) -> int:
    points = agent.store.history(our_sku, competitor, days=days)
    if not points:
        print(f"no history for {our_sku} @ {competitor} in last {days} days")
        return 1
    print(f"{our_sku} @ {competitor} - last {days} days ({len(points)} points):")
    for p in points:
        stock = "" if p.in_stock is None else (" in-stock" if p.in_stock else " OOS")
        print(
            f"  {p.captured_at.isoformat(timespec='seconds')}  "
            f"${p.price:>9} {p.currency}  [{p.extractor_method:9} conf={p.confidence:.2f}]"
            f"{stock}"
        )
    return 0


def cmd_changes(agent: PriceIntelligenceAgent, hours: int) -> int:
    rows = agent.store.recent_changes(hours=hours)
    if not rows:
        print(f"no price changes in the last {hours} hours")
        return 0
    print(f"Price changes in last {hours} hours:")
    for r in rows:
        pct = r["change_percent"]
        arrow = "↑" if pct > 0 else "↓"
        print(
            f"  {r['detected_at']}  {arrow} {r['our_sku']:18} @ "
            f"{r['competitor']:14} ${r['old_price']} → ${r['new_price']} ({pct:+.1f}%)"
        )
    return 0


def cmd_verify_audit(agent: PriceIntelligenceAgent) -> int:
    ok, n, bad = agent.audit.verify()
    if ok:
        print(f"✓ audit log intact ({n} entries verified)")
        return 0
    print(f"✗ audit log TAMPERED: {bad} (verified {n} good entries before failure)")
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agents.price_intelligence",
        description="Neural Hardware Price Intelligence Agent (1C)",
    )
    parser.add_argument(
        "--config", default="config/competitors.yaml", help="competitor config YAML"
    )
    parser.add_argument("--data-dir", default="data", help="data directory")
    parser.add_argument("-v", "--verbose", action="store_true")

    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan", help="scan all enabled SKUs once")
    sub.add_parser("list", help="list configured competitors and SKUs")

    p_hist = sub.add_parser("history", help="show price history for one SKU+competitor")
    p_hist.add_argument("our_sku")
    p_hist.add_argument("competitor")
    p_hist.add_argument("--days", type=int, default=30)

    p_chg = sub.add_parser("changes", help="show recent price changes")
    p_chg.add_argument("--hours", type=int, default=24)

    sub.add_parser("verify-audit", help="verify the audit log hash chain")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    try:
        agent = PriceIntelligenceAgent(args.config, data_dir=args.data_dir)
    except Exception as exc:
        print(f"failed to initialise agent: {exc}", file=sys.stderr)
        return 1

    match args.cmd:
        case "scan":
            return cmd_scan(agent)
        case "list":
            return cmd_list(agent)
        case "history":
            return cmd_history(agent, args.our_sku, args.competitor, args.days)
        case "changes":
            return cmd_changes(agent, args.hours)
        case "verify-audit":
            return cmd_verify_audit(agent)
        case _:
            parser.print_help()
            return 1


if __name__ == "__main__":
    sys.exit(main())
