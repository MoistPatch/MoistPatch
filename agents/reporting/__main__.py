from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from .agent import ReportingAgent


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _agent(data_dir: Path) -> ReportingAgent:
    return ReportingAgent(
        db_path=data_dir / "prices.db",
        audit_path=data_dir / "audit.jsonl",
    )


def cmd_render(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    agent = _agent(data_dir)
    report = agent.build_report(
        hours=args.hours,
        product_filter=args.sku or None,
        is_demo=False,
    )
    subject, html, text = agent.render(report, window_hours=args.hours)

    if args.format == "html":
        target = Path(args.out) if args.out else None
        if target:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(html, encoding="utf-8")
            print(f"wrote HTML report ({len(html)} bytes) -> {target}")
        else:
            sys.stdout.write(html)
    else:
        sys.stdout.write(text)

    return 0


def cmd_send(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    agent = _agent(data_dir)
    report = agent.build_report(
        hours=args.hours,
        product_filter=args.sku or None,
        is_demo=False,
    )
    if args.dry_run:
        subject, html, text = agent.render(report, window_hours=args.hours)
        print(f"--- SUBJECT ---\n{subject}\n")
        print(f"--- TO ---\n{args.to}\n")
        if args.bcc:
            print(f"--- BCC ---\n{args.bcc}\n")
        print(f"--- TEXT BODY ({len(text)} bytes) ---\n{text}")
        return 0
    try:
        subject = agent.send_report(
            report, to=args.to, bcc=args.bcc, window_hours=args.hours
        )
        print(f"✓ sent: {subject!r} -> {args.to}")
        return 0
    except RuntimeError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2


def cmd_demo_data(args: argparse.Namespace) -> int:
    """Populate the DB with clearly-labelled fixture data so you can preview
    what the email will look like before wiring up real scraping."""
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "prices.db"

    # Use the price-intelligence storage layer to create the schema, then
    # insert fictional rows tagged with the literal string 'DEMO' in the URL.
    from agents.price_intelligence.storage import PriceStore
    from agents.price_intelligence.models import PricePoint

    store = PriceStore(db_path)
    now = datetime.now(timezone.utc)

    demo_rows = [
        # NH-RTX5090 across 4 competitors (clearly marked DEMO in URL)
        ("NH-RTX5090", "Centre Com",    Decimal("3499.00"), True,  "jsonld",    0.98),
        ("NH-RTX5090", "Mwave",         Decimal("3399.00"), True,  "opengraph", 0.92),
        ("NH-RTX5090", "Scorptec",      Decimal("3549.00"), False, "jsonld",    0.98),
        ("NH-RTX5090", "PLE Computers", Decimal("3479.00"), True,  "microdata", 0.88),
        # NH-RX9070XT across 3
        ("NH-RX9070XT", "Centre Com",   Decimal("1099.00"), True,  "jsonld",    0.98),
        ("NH-RX9070XT", "Mwave",        Decimal("1149.00"), True,  "jsonld",    0.98),
        ("NH-RX9070XT", "Umart",        Decimal("1059.00"), True,  "selector",  0.80),
        # NH-ARCTIC360
        ("NH-ARCTIC360", "PLE Computers", Decimal("149.00"), True, "jsonld",    0.98),
        ("NH-ARCTIC360", "Centre Com",    Decimal("169.00"), True, "opengraph", 0.92),
    ]

    inserted = 0
    for sku, comp, price, in_stock, method, conf in demo_rows:
        store.record_point(
            PricePoint(
                our_sku=sku,
                competitor=comp,
                url=f"https://DEMO.example.com/{comp.lower().replace(' ', '-')}/{sku}",
                price=price,
                currency="AUD",
                in_stock=in_stock,
                captured_at=now,
                extractor_method=method,
                confidence=conf,
                raw_html_excerpt="(demo fixture)",
            )
        )
        inserted += 1

    # Add a fake price change for variety
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """INSERT INTO price_changes
               (our_sku, competitor, old_price, new_price,
                change_amount, change_percent, detected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "NH-RTX5090",
                "Mwave",
                "3499.00",
                "3399.00",
                "-100.00",
                -2.86,
                (now - timedelta(hours=6)).isoformat(),
            ),
        )

    print(f"populated {db_path} with {inserted} DEMO rows + 1 demo change.")
    print("Render the demo report with:")
    print(f"  python -m agents.reporting render --demo-tag --data-dir {data_dir}")
    print(f"  python -m agents.reporting render --demo-tag --data-dir {data_dir} --format html --out data/sample-report.html")
    return 0


def cmd_render_demo(args: argparse.Namespace) -> int:
    """Like 'render' but explicitly tags the report as DEMO."""
    data_dir = Path(args.data_dir)
    agent = _agent(data_dir)
    report = agent.build_report(
        hours=args.hours,
        product_filter=args.sku or None,
        is_demo=True,
    )
    subject, html, text = agent.render(report, window_hours=args.hours)
    if args.format == "html":
        target = Path(args.out) if args.out else None
        if target:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(html, encoding="utf-8")
            print(f"wrote DEMO HTML report ({len(html)} bytes) -> {target}")
        else:
            sys.stdout.write(html)
    else:
        sys.stdout.write(text)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agents.reporting",
        description="Neural Hardware Agent 11 — Daily Reporting",
    )
    parser.add_argument("--data-dir", default="data", help="data directory")
    parser.add_argument("-v", "--verbose", action="store_true")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_render = sub.add_parser("render", help="render the report to stdout or a file")
    p_render.add_argument("--hours", type=int, default=24)
    p_render.add_argument("--sku", action="append", help="filter to specific SKU(s)")
    p_render.add_argument("--format", choices=("html", "text"), default="text")
    p_render.add_argument("--out", help="write HTML to this path instead of stdout")
    p_render.set_defaults(func=cmd_render)

    p_send = sub.add_parser("send", help="send the report via Gmail SMTP")
    p_send.add_argument("--to", required=True, help="recipient email address")
    p_send.add_argument("--bcc", default=os.environ.get("REPORT_BCC"))
    p_send.add_argument("--hours", type=int, default=24)
    p_send.add_argument("--sku", action="append", help="filter to specific SKU(s)")
    p_send.add_argument("--dry-run", action="store_true",
                        help="render to stdout instead of sending")
    p_send.set_defaults(func=cmd_send)

    p_demo = sub.add_parser("demo-data", help="populate DB with fixture data (clearly tagged)")
    p_demo.set_defaults(func=cmd_demo_data)

    p_render_demo = sub.add_parser("render-demo", help="render with DEMO banner")
    p_render_demo.add_argument("--hours", type=int, default=24)
    p_render_demo.add_argument("--sku", action="append")
    p_render_demo.add_argument("--format", choices=("html", "text"), default="text")
    p_render_demo.add_argument("--out")
    p_render_demo.set_defaults(func=cmd_render_demo)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
