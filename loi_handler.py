#!/usr/bin/env python3
"""
loi_handler.py — Vantyx LOI Email Handler
==========================================
Lightweight HTTP server that accepts POST /submit-loi (JSON),
formats the LOI, and emails it to sam@vantyx.com.au via SMTP.

Usage
-----
  export SMTP_USER="yourgmail@gmail.com"
  export SMTP_PASS="xxxx xxxx xxxx xxxx"   # Gmail App Password
  export LOI_RECIPIENT="sam@vantyx.com.au"  # optional override
  python loi_handler.py                     # listens on port 8080

Environment variables
---------------------
  SMTP_USER       Gmail address used to send (required)
  SMTP_PASS       Gmail App Password — NOT your Google account password (required)
  SMTP_HOST       SMTP server  (default: smtp.gmail.com)
  SMTP_PORT       SMTP port    (default: 587)
  LOI_RECIPIENT   Recipient address (default: sam@vantyx.com.au)
  LOI_HOST        Bind host (default: 0.0.0.0)
  LOI_PORT        Bind port (default: 8080)

Generating a Gmail App Password
--------------------------------
  1. Go to https://myaccount.google.com/security
  2. Enable 2-Step Verification
  3. Go to https://myaccount.google.com/apppasswords
  4. Create an app password and export it as SMTP_PASS
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from http.server import BaseHTTPRequestHandler, HTTPServer
from textwrap import dedent
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("loi_handler")

LOI_RECIPIENT  = os.environ.get("LOI_RECIPIENT", "sam@vantyx.com.au")
VANTYX_ABN     = "84 544 119 830"
VANTYX_PHONE   = "0431 367 255"
VANTYX_SITE    = "www.vantyx.com.au"
VANTYX_BIO     = "International Commodity Trader & Importer/Exporter of Agricultural Fertiliser Products"


# ---------------------------------------------------------------------------
# Email content builders
# ---------------------------------------------------------------------------

def _fmt_date(iso_date: str) -> str:
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d %B %Y")
    except ValueError:
        return iso_date


def build_text_body(d: dict[str, Any]) -> str:
    date_str  = _fmt_date(d.get("loiDate", ""))
    product   = d.get("productType", "")
    if d.get("otherProduct"):
        product += f" — {d['otherProduct']}"
    farmsize  = f"{d['farmSize']} Ha" if d.get("farmSize") else "N/A"
    notes     = d.get("additionalNotes") or "None provided."

    return dedent(f"""\
        ============================================================
        SUPPLY ENQUIRY — FERTILISER PRODUCTS
        ============================================================
        FROM:  {d.get('businessName', '')}
        TO:    Vantyx Pty Ltd (ABN {VANTYX_ABN})
        DATE:  {date_str}
        ============================================================

        1. ENQUIRER DETAILS
           Name / Title:        {d.get('fullName', '')}
           Farm / Business:     {d.get('businessName', '')}
           ABN:                 {d.get('abn') or 'N/A'}
           Email:               {d.get('email', '')}
           Phone:               {d.get('phone') or 'N/A'}

        2. SUPPLY REQUIREMENTS
           Product Type:        {product}
           Annual Volume:       {d.get('annualVolume', '')} Tonnes (Metric) per year
           Delivery Address:    {d.get('deliveryAddress', '')}
           Primary Application: {d.get('primaryApplication', '')}
           Farm Size:           {farmsize}
           Delivery Schedule:   {d.get('deliverySchedule', '')}

        3. ADDITIONAL NOTES
           {notes}

        4. CONFIRMATION
           [✓] Non-binding enquiry acknowledged
           [✓] No financial commitment
           [✓] Consent to be contacted by Vantyx

        ============================================================
        NOTE: This enquiry is non-binding. No financial obligation
        arises. Individual orders are subject to separate purchase
        agreements with agreed pricing, delivery terms, and payment
        conditions at the time of order.
        ============================================================
        Submitted: {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}
        Source:    {VANTYX_SITE}/enquiry
    """)


def build_html_body(d: dict[str, Any]) -> str:
    date_str = _fmt_date(d.get("loiDate", ""))
    product  = d.get("productType", "")
    if d.get("otherProduct"):
        product += f" — {d['otherProduct']}"
    farmsize = f"{d['farmSize']} Ha" if d.get("farmSize") else "N/A"
    notes_html = (d.get("additionalNotes") or "None provided.").replace("\n", "<br>")

    def row(label: str, value: str) -> str:
        v = value if value and value != "N/A" else '<span style="color:#999;">N/A</span>'
        return (
            f'<tr><td style="padding:8px 12px;font-weight:600;color:#3d4f3a;'
            f'white-space:nowrap;vertical-align:top;">{label}</td>'
            f'<td style="padding:8px 12px;color:#1a2214;">{v}</td></tr>'
        )

    submitted_at = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Supply Enquiry – {d.get('businessName','')}</title></head>
<body style="margin:0;padding:0;background:#f4f9f5;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f9f5;padding:32px 0;">
<tr><td align="center">
<table width="620" cellpadding="0" cellspacing="0"
  style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(10,51,32,0.12);">

  <!-- Header -->
  <tr><td style="background:#145232;padding:28px 36px;">
    <p style="margin:0;font-family:Georgia,serif;font-size:22px;font-weight:700;
      color:#fff;letter-spacing:0.3px;">VANTYX PTY LTD</p>
    <p style="margin:4px 0 0;font-size:12px;color:rgba(255,255,255,0.6);letter-spacing:0.5px;">
      ABN {VANTYX_ABN} &nbsp;|&nbsp; Melbourne, Victoria &nbsp;|&nbsp;
      sam@vantyx.com.au &nbsp;|&nbsp; {VANTYX_PHONE}
    </p>
    <p style="margin:4px 0 0;font-size:11px;color:rgba(255,255,255,0.45);">
      {VANTYX_BIO}
    </p>
    <p style="margin:16px 0 0;font-size:20px;font-weight:700;color:#d4a017;
      font-family:Georgia,serif;letter-spacing:1px;">SUPPLY ENQUIRY</p>
    <p style="margin:4px 0 0;font-size:13px;color:rgba(255,255,255,0.65);">
      Fertiliser Supply Enquiry
    </p>
  </td></tr>

  <!-- Meta row -->
  <tr><td style="background:#f0f7f3;border-bottom:1px solid #c8dcc4;padding:16px 36px;">
    <table cellpadding="0" cellspacing="0" width="100%">
    <tr>
      <td style="font-size:13px;color:#3d4f3a;">
        <strong>FROM:</strong> {d.get('businessName','')}
      </td>
      <td align="right" style="font-size:13px;color:#3d4f3a;">
        <strong>DATE:</strong> {date_str}
      </td>
    </tr>
    <tr><td colspan="2" style="font-size:13px;color:#3d4f3a;padding-top:4px;">
      <strong>TO:</strong> Vantyx Pty Ltd
    </td></tr>
    </table>
  </td></tr>

  <!-- Body -->
  <tr><td style="padding:28px 36px;">

    <!-- Enquirer Details -->
    <p style="font-size:14px;font-weight:700;color:#145232;text-transform:uppercase;
      letter-spacing:1px;margin:0 0 10px;border-bottom:2px solid #c8dcc4;padding-bottom:8px;">
      1. Enquirer Details
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"
      style="border:1px solid #c8dcc4;border-radius:8px;overflow:hidden;margin-bottom:24px;font-size:14px;">
      {row('Full Name / Title', d.get('fullName',''))}
      {row('Farm / Business', d.get('businessName',''))}
      {row('ABN', d.get('abn') or 'N/A')}
      {row('Contact Email', d.get('email',''))}
      {row('Phone', d.get('phone') or 'N/A')}
    </table>

    <!-- Supply Requirements -->
    <p style="font-size:14px;font-weight:700;color:#145232;text-transform:uppercase;
      letter-spacing:1px;margin:0 0 10px;border-bottom:2px solid #c8dcc4;padding-bottom:8px;">
      2. Supply Requirements
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"
      style="border:1px solid #c8dcc4;border-radius:8px;overflow:hidden;margin-bottom:24px;font-size:14px;">
      {row('Product Type', product)}
      {row('Annual Volume', f"{d.get('annualVolume','')} Tonnes (Metric) per year")}
      {row('Delivery Address', d.get('deliveryAddress',''))}
      {row('Primary Application', d.get('primaryApplication',''))}
      {row('Farm Size', farmsize)}
      {row('Delivery Schedule', d.get('deliverySchedule',''))}
    </table>

    <!-- Notes -->
    <p style="font-size:14px;font-weight:700;color:#145232;text-transform:uppercase;
      letter-spacing:1px;margin:0 0 10px;border-bottom:2px solid #c8dcc4;padding-bottom:8px;">
      3. Additional Notes
    </p>
    <div style="background:#f9f7f1;border:1px solid #c8dcc4;border-radius:8px;
      padding:14px 18px;font-size:14px;color:#3d4f3a;margin-bottom:24px;line-height:1.6;">
      {notes_html}
    </div>

    <!-- Confirmation -->
    <p style="font-size:14px;font-weight:700;color:#145232;text-transform:uppercase;
      letter-spacing:1px;margin:0 0 10px;border-bottom:2px solid #c8dcc4;padding-bottom:8px;">
      4. Confirmation
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"
      style="margin-bottom:24px;font-size:14px;color:#3d4f3a;">
      <tr><td style="padding:5px 0;">
        <span style="color:#27ae60;font-weight:700;">&#10003;</span>&nbsp;
        <strong>Non-binding:</strong> This enquiry is not a legally binding contract. No deposit or obligation arises.
      </td></tr>
      <tr><td style="padding:5px 0;">
        <span style="color:#27ae60;font-weight:700;">&#10003;</span>&nbsp;
        <strong>Contact consent:</strong> Enquirer consents to Vantyx Pty Ltd making contact to discuss supply options.
      </td></tr>
    </table>

    <!-- Disclaimer -->
    <div style="background:#fdf3d0;border:1px solid #e8c96a;border-radius:8px;
      padding:14px 18px;font-size:12px;color:#7a5a00;line-height:1.6;margin-bottom:8px;">
      <strong>NOTE:</strong> This enquiry is non-binding. No financial obligation arises.
      Individual orders will be subject to separate purchase agreements with agreed pricing, delivery terms,
      and payment conditions at the time of order.
    </div>

  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#0a3320;padding:20px 36px;text-align:center;">
    <p style="margin:0;font-size:12px;color:rgba(255,255,255,0.55);">
      <strong style="color:rgba(255,255,255,0.8);">Vantyx Pty Ltd</strong>
      &nbsp;&middot;&nbsp; ABN {VANTYX_ABN}
      &nbsp;&middot;&nbsp; Melbourne, Victoria<br>
      <a href="mailto:sam@vantyx.com.au"
        style="color:#d4a017;">sam@vantyx.com.au</a>
      &nbsp;&middot;&nbsp; {VANTYX_PHONE}
      &nbsp;&middot;&nbsp;
      <a href="https://{VANTYX_SITE}" style="color:#d4a017;">{VANTYX_SITE}</a>
    </p>
    <p style="margin:10px 0 0;font-size:11px;color:rgba(255,255,255,0.35);">
      Submitted {submitted_at} via {VANTYX_SITE}/enquiry
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def build_confirmation_html(d: dict[str, Any]) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>LOI Received – Vantyx</title></head>
<body style="margin:0;padding:0;background:#f4f9f5;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:32px 0;">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0"
  style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(10,51,32,0.12);">
  <tr><td style="background:#145232;padding:24px 32px;text-align:center;">
    <p style="margin:0;font-family:Georgia,serif;font-size:20px;font-weight:700;color:#fff;">
      VANTYX PTY LTD
    </p>
    <p style="margin:6px 0 0;font-size:14px;color:rgba(255,255,255,0.65);">International Commodity Trader &amp; Importer/Exporter of Agricultural Fertiliser Products</p>
  </td></tr>
  <tr><td style="padding:32px;">
    <p style="font-size:28px;margin:0 0 8px;text-align:center;">&#9989;</p>
    <h2 style="font-size:20px;color:#145232;text-align:center;margin:0 0 16px;
      font-family:Georgia,serif;">Enquiry Received</h2>
    <p style="font-size:15px;color:#3d4f3a;line-height:1.6;margin:0 0 20px;">
      Thank you, <strong>{d.get('fullName','')}</strong>. We've received your supply enquiry
      for <strong>{d.get('businessName','')}</strong>. Sam will be in touch within one business
      day to discuss fertiliser supply options for your operation.
    </p>
    <div style="background:#f0f7f3;border:1px solid #c8dcc4;border-radius:8px;
      padding:16px 20px;margin-bottom:20px;font-size:14px;color:#3d4f3a;">
      <p style="margin:0 0 6px;"><strong>Product:</strong> {d.get('productType','')}</p>
      <p style="margin:0 0 6px;"><strong>Volume:</strong> {d.get('annualVolume','')} T/yr</p>
      <p style="margin:0;"><strong>Reference email:</strong> {d.get('email','')}</p>
    </div>
    <p style="font-size:13px;color:#6b7c68;line-height:1.5;margin:0;">
      In the meantime, contact Sam at
      <a href="mailto:sam@vantyx.com.au" style="color:#1b6b3a;">sam@vantyx.com.au</a>
      or <a href="tel:0431367255" style="color:#1b6b3a;">{VANTYX_PHONE}</a>.
    </p>
  </td></tr>
  <tr><td style="background:#0a3320;padding:16px;text-align:center;">
    <p style="margin:0;font-size:12px;color:rgba(255,255,255,0.5);">
      &copy; Vantyx Pty Ltd &nbsp;&middot;&nbsp; ABN {VANTYX_ABN}
    </p>
  </td></tr>
</table></td></tr></table>
</body></html>"""


# ---------------------------------------------------------------------------
# SMTP sender
# ---------------------------------------------------------------------------

def _smtp_config() -> dict[str, Any]:
    # Default SMTP_USER to the recipient address (works for Google Workspace / Gmail)
    default_user = os.environ.get("SMTP_USER", LOI_RECIPIENT)
    if not os.environ.get("SMTP_PASS"):
        raise RuntimeError(
            "SMTP_PASS is not set. "
            "Generate a Gmail App Password at https://myaccount.google.com/apppasswords "
            "and export it as SMTP_PASS."
        )
    user = default_user
    return {
        "host":      os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "port":      int(os.environ.get("SMTP_PORT", "587")),
        "user":      user,
        "password":  os.environ["SMTP_PASS"],
        "from_addr": os.environ.get("SMTP_FROM_ADDR", LOI_RECIPIENT),
        "from_name": os.environ.get("SMTP_FROM_NAME", "Vantyx Pty Ltd"),
    }


def send_loi_email(data: dict[str, Any]) -> None:
    cfg = _smtp_config()
    date_str = _fmt_date(data.get("loiDate", ""))
    business = data.get("businessName", "Unknown")
    product  = data.get("productType", "")

    # --- Notification email to Vantyx (sam@vantyx.com.au) ---
    msg_notify = EmailMessage()
    msg_notify["From"]       = formataddr((cfg["from_name"], cfg["from_addr"]))
    msg_notify["To"]         = LOI_RECIPIENT
    msg_notify["Reply-To"]   = data.get("email", "")
    msg_notify["Subject"]    = f"New Enquiry: {business} — {product} — {date_str}"
    msg_notify["Message-ID"] = make_msgid(domain=cfg["from_addr"].split("@", 1)[-1])
    msg_notify["X-Agent"]    = "vantyx/loi-handler"
    msg_notify.set_content(build_text_body(data))
    msg_notify.add_alternative(build_html_body(data), subtype="html")

    # --- Confirmation email to the buyer ---
    buyer_email = data.get("email", "")
    msg_confirm = None
    if buyer_email:
        msg_confirm = EmailMessage()
        msg_confirm["From"]       = formataddr(("Vantyx Pty Ltd", cfg["from_addr"]))
        msg_confirm["To"]         = buyer_email
        msg_confirm["Reply-To"]   = LOI_RECIPIENT
        msg_confirm["Subject"]    = f"Vantyx – Enquiry Received: {business}"
        msg_confirm["Message-ID"] = make_msgid(domain=cfg["from_addr"].split("@", 1)[-1])
        msg_confirm["X-Agent"]    = "vantyx/loi-handler"
        confirm_text = (
            f"Thank you, {data.get('fullName', '')}.\n\n"
            f"We've received your supply enquiry for {business}. "
            f"Sam will be in touch within one business day.\n\n"
            f"Contact: sam@vantyx.com.au | {VANTYX_PHONE}\n\n"
            "— Vantyx Pty Ltd"
        )
        msg_confirm.set_content(confirm_text)
        msg_confirm.add_alternative(build_confirmation_html(data), subtype="html")

    log.info("connecting to %s:%d …", cfg["host"], cfg["port"])
    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(cfg["user"], cfg["password"])
        smtp.send_message(msg_notify)
        log.info("LOI notification sent to %s", LOI_RECIPIENT)
        if msg_confirm:
            smtp.send_message(msg_confirm)
            log.info("Confirmation sent to %s", buyer_email)


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class LOIHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt: str, *args: Any) -> None:
        log.info(fmt, *args)

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "service": "vantyx-loi-handler"})
        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if self.path != "/submit-loi":
            self._send_json(404, {"error": "Not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        if length > 64_000:
            self._send_json(413, {"error": "Payload too large"})
            return

        try:
            raw  = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._send_json(400, {"error": f"Invalid JSON: {exc}"})
            return

        # Basic server-side validation
        required = ("fullName", "businessName", "email", "productType",
                    "annualVolume", "deliveryAddress", "primaryApplication",
                    "deliverySchedule")
        missing = [f for f in required if not str(data.get(f, "")).strip()]
        if missing:
            self._send_json(422, {"error": f"Missing fields: {', '.join(missing)}"})
            return

        try:
            send_loi_email(data)
        except RuntimeError as exc:
            log.error("SMTP config error: %s", exc)
            self._send_json(503, {"error": str(exc)})
            return
        except smtplib.SMTPException as exc:
            log.error("SMTP error: %s", exc)
            self._send_json(502, {"error": f"Email delivery failed: {exc}"})
            return

        self._send_json(200, {
            "ok":      True,
            "message": "LOI submitted successfully.",
            "to":      LOI_RECIPIENT,
        })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    host = os.environ.get("LOI_HOST", "0.0.0.0")
    port = int(os.environ.get("LOI_PORT", "8080"))

    missing_smtp = [k for k in ("SMTP_USER", "SMTP_PASS") if not os.environ.get(k)]
    if missing_smtp:
        log.warning(
            "SMTP credentials not set (%s). "
            "The form will fall back to mailto: in the browser. "
            "Set SMTP_USER and SMTP_PASS to enable direct email delivery.",
            ", ".join(missing_smtp),
        )

    log.info("Vantyx LOI handler starting on %s:%d", host, port)
    log.info("LOI notifications will be sent to: %s", LOI_RECIPIENT)

    server = HTTPServer((host, port), LOIHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down.")
        server.server_close()
