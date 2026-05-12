from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from agents.price_intelligence.audit import AuditLog

from .compiler import DailyReport, ReportCompiler
from .sender import SmtpConfig, build_message, send


log = logging.getLogger(__name__)


class ReportingAgent:
    """Agent 11: Daily/Monthly Reporting.

    Read-only consumer of the Price Intelligence database.
    Renders both HTML and text email bodies and (optionally) delivers them
    via SMTP. Refuses to send when report.is_demo unless force_demo=True.
    """

    AGENT_ID = "price-reporter-11"

    def __init__(
        self,
        db_path: Path | str,
        *,
        audit_path: Optional[Path | str] = None,
        templates_dir: Optional[Path] = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.audit_path = Path(audit_path) if audit_path else None
        self.compiler = ReportCompiler(self.db_path)
        self._templates_dir = templates_dir or Path(__file__).parent / "templates"
        self._env = Environment(
            loader=FileSystemLoader(self._templates_dir),
            autoescape=select_autoescape(enabled_extensions=("html", "html.j2")),
            keep_trailing_newline=True,
            trim_blocks=False,
            lstrip_blocks=False,
        )

    def build_report(
        self,
        *,
        hours: int = 24,
        product_filter: Optional[list[str]] = None,
        is_demo: bool = False,
    ) -> DailyReport:
        report = self.compiler.compile(
            hours=hours, product_filter=product_filter, is_demo=is_demo
        )
        # Append audit-chain integrity check
        if self.audit_path and self.audit_path.exists():
            audit = AuditLog(self.audit_path)
            ok, n, _ = audit.verify()
            report.audit_chain_ok = ok
            report.audit_entries = n
        return report

    def render(
        self, report: DailyReport, *, window_hours: int = 24, subject: Optional[str] = None
    ) -> tuple[str, str, str]:
        """Returns (subject, html_body, text_body)."""
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        default_subject = f"[Neural Hardware] Daily price report — {date_str}"
        if report.is_demo:
            default_subject = "[DEMO] " + default_subject
        if subject is None:
            subject = default_subject

        ctx = {"report": report, "subject": subject, "window_hours": window_hours}
        html = self._env.get_template("daily.html.j2").render(**ctx)
        text = self._env.get_template("daily.txt.j2").render(**ctx)
        return subject, html, text

    def send_report(
        self,
        report: DailyReport,
        *,
        to: str,
        bcc: Optional[str] = None,
        window_hours: int = 24,
        force_demo: bool = False,
    ) -> str:
        if report.is_demo and not force_demo:
            raise RuntimeError(
                "refusing to send a DEMO report. Pass force_demo=True if you "
                "are sure you want to email fixture data."
            )
        subject, html_body, text_body = self.render(
            report, window_hours=window_hours
        )
        config = SmtpConfig.from_env()
        msg = build_message(
            config=config,
            to=to,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            bcc=bcc,
            reply_to=None,
        )
        send(config, msg)
        return subject
