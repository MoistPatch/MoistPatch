from __future__ import annotations

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Optional


log = logging.getLogger(__name__)


@dataclass
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    from_name: str
    from_addr: str
    use_starttls: bool = True

    @classmethod
    def from_env(cls) -> "SmtpConfig":
        """Read credentials from environment variables.

        Required:
          SMTP_USER   — sending Gmail address (e.g. neuralhardware.bot@gmail.com)
          SMTP_PASS   — Gmail App Password (16 chars, NOT your account password)

        Optional (with sensible defaults):
          SMTP_HOST       (default smtp.gmail.com)
          SMTP_PORT       (default 587)
          SMTP_FROM_NAME  (default "Neural Hardware Agent 11")
          SMTP_FROM_ADDR  (default same as SMTP_USER)
        """
        missing = [k for k in ("SMTP_USER", "SMTP_PASS") if not os.environ.get(k)]
        if missing:
            raise RuntimeError(
                f"missing required SMTP env vars: {missing}. "
                f"Generate a Gmail App Password at "
                f"https://myaccount.google.com/apppasswords and export it as SMTP_PASS."
            )
        user = os.environ["SMTP_USER"]
        return cls(
            host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
            port=int(os.environ.get("SMTP_PORT", "587")),
            user=user,
            password=os.environ["SMTP_PASS"],
            from_name=os.environ.get("SMTP_FROM_NAME", "Neural Hardware Agent 11"),
            from_addr=os.environ.get("SMTP_FROM_ADDR", user),
            use_starttls=True,
        )


def build_message(
    *,
    config: SmtpConfig,
    to: str,
    subject: str,
    html_body: str,
    text_body: str,
    bcc: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((config.from_name, config.from_addr))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=config.from_addr.split("@", 1)[-1])
    if reply_to:
        msg["Reply-To"] = reply_to
    if bcc:
        msg["Bcc"] = bcc
    msg["X-Agent"] = "neural-hardware/price-reporter-11"
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    return msg


def send(config: SmtpConfig, msg: EmailMessage) -> None:
    """Connect via STARTTLS and send. Raises on any failure."""
    log.info(
        "connecting to %s:%d as %s …", config.host, config.port, config.user
    )
    with smtplib.SMTP(config.host, config.port, timeout=30) as smtp:
        smtp.ehlo()
        if config.use_starttls:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        smtp.login(config.user, config.password)
        smtp.send_message(msg)
    log.info("delivered: %s -> %s", msg["Subject"], msg["To"])
