"""Lead capture, storage, and forwarding via SMTP."""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .content import generate_lead_response
from .models import Lead
from .storage import get_unforwarded_leads, save_lead


def capture_lead(
    source: str,
    name: str | None = None,
    email: str | None = None,
    company: str | None = None,
    product_interest: str | None = None,
    quantity_mt: float | None = None,
    message: str | None = None,
) -> Lead:
    """Save a new lead and trigger immediate forwarding."""
    lead = Lead(
        source=source,
        name=name,
        email=email,
        company=company,
        product_interest=product_interest,
        quantity_mt=quantity_mt,
        message=message,
    )
    lead = save_lead(lead)
    _forward_lead(lead)
    return lead


def forward_pending_leads() -> int:
    """Forward all un-forwarded leads. Returns count forwarded."""
    leads = get_unforwarded_leads()
    count = 0
    for lead in leads:
        try:
            _forward_lead(lead)
            count += 1
        except Exception as exc:
            print(f"[leads] Failed to forward lead {lead.id}: {exc}")
    return count


def _forward_lead(lead: Lead) -> None:
    """Email lead details to sam@vantyx.com.au and optionally reply to the lead."""
    smtp_user = os.environ.get("SMTP_USER", "sam@vantyx.com.au")
    smtp_pass = os.environ["SMTP_PASS"]
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    recipient = os.environ.get("LOI_RECIPIENT", "sam@vantyx.com.au")

    # Build internal notification
    lines = [
        "<h2>New Lead — Vantyx Marketing Agent</h2>",
        f"<p><strong>Source:</strong> {lead.source}</p>",
    ]
    if lead.name:
        lines.append(f"<p><strong>Name:</strong> {lead.name}</p>")
    if lead.company:
        lines.append(f"<p><strong>Company:</strong> {lead.company}</p>")
    if lead.email:
        lines.append(f"<p><strong>Email:</strong> {lead.email}</p>")
    if lead.product_interest:
        lines.append(f"<p><strong>Product interest:</strong> {lead.product_interest}</p>")
    if lead.quantity_mt:
        lines.append(f"<p><strong>Quantity (MT):</strong> {lead.quantity_mt}</p>")
    if lead.message:
        lines.append(f"<p><strong>Message:</strong> {lead.message}</p>")
    lines.append(f"<p><em>Received: {lead.created_at.strftime('%d %b %Y %H:%M UTC')}</em></p>")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Vantyx Lead] {lead.name or 'Unknown'} — {lead.product_interest or lead.source}"
    msg["From"] = smtp_user
    msg["To"] = recipient
    msg.attach(MIMEText("\n".join(
        l.replace("<h2>", "").replace("</h2>", "").replace("<p>", "")
        .replace("</p>", "").replace("<strong>", "").replace("</strong>", "")
        .replace("<em>", "").replace("</em>", "")
        for l in lines
    ), "plain"))
    msg.attach(MIMEText("".join(lines), "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)

    # Send personalised follow-up to the lead if we have their email
    if lead.email and lead.name:
        try:
            body = generate_lead_response(
                lead.name,
                lead.product_interest or "fertiliser products",
                lead.company or "your organisation",
            )
            reply = MIMEMultipart("alternative")
            reply["Subject"] = "Thank you for your enquiry — Vantyx Pty Ltd"
            reply["From"] = smtp_user
            reply["To"] = lead.email
            reply["Reply-To"] = recipient
            plain = f"Dear {lead.name},\n\n{body}\n\nKind regards,\nSam\nVantyx Pty Ltd\nsam@vantyx.com.au | 0431 367 255"
            html_body = f"<p>Dear {lead.name},</p><p>{body.replace(chr(10), '</p><p>')}</p><p>Kind regards,<br>Sam<br>Vantyx Pty Ltd<br><a href='mailto:sam@vantyx.com.au'>sam@vantyx.com.au</a></p>"
            reply.attach(MIMEText(plain, "plain"))
            reply.attach(MIMEText(html_body, "html"))
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(reply)
        except Exception as exc:
            print(f"[leads] Follow-up email failed for {lead.email}: {exc}")

    lead.forwarded = True
    save_lead(lead)
