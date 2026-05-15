#!/usr/bin/env python3
"""
Vantyx unified local server.
Serves the website, LOI form, agent dashboard, and all agent REST APIs.

Usage:  python server.py
Opens:  http://localhost:8080          — Vantyx website
        http://localhost:8080/loi      — LOI form
        http://localhost:8080/dashboard — Agent dashboard
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any

# ── Env loading (reads .env before any agent import) ──────────────────────
_ROOT = Path(__file__).parent
_ENV = _ROOT / ".env"
if _ENV.exists():
    for _line in _ENV.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("vantyx.server")

# ── Agent singletons (lazy-loaded so server starts even if a dep is missing) ──

_marketing_agent = None
_pricing_agent = None
_surveillance_agent = None
_claudia_agent = None


def _marketing():
    global _marketing_agent
    if _marketing_agent is None:
        from agents.marketing import MarketingAgent
        _marketing_agent = MarketingAgent()
    return _marketing_agent


def _pricing():
    global _pricing_agent
    if _pricing_agent is None:
        from agents.pricing import PricingAgent
        _pricing_agent = PricingAgent()
    return _pricing_agent


def _surveillance():
    global _surveillance_agent
    if _surveillance_agent is None:
        from agents.surveillance import SurveillanceAgent
        _surveillance_agent = SurveillanceAgent()
    return _surveillance_agent


def _claudia():
    global _claudia_agent
    if _claudia_agent is None:
        from agents.claudia import ClaudiaAgent
        _claudia_agent = ClaudiaAgent()
    return _claudia_agent


# ── LOI email logic (reuse from loi_handler) ──────────────────────────────
try:
    from loi_handler import send_loi_email
    _LOI_OK = True
except ImportError:
    _LOI_OK = False
    log.warning("loi_handler.py not found — /submit-loi will return 503")


# ── Static file map ───────────────────────────────────────────────────────
_STATIC: dict[str, Path] = {
    "/":            _ROOT / "vantyx" / "index.html",
    "/index.html":  _ROOT / "vantyx" / "index.html",
    "/loi":         _ROOT / "loi.html",
    "/loi.html":    _ROOT / "loi.html",
    "/dashboard":   _ROOT / "dashboard.html",
}


# ── HTTP handler ──────────────────────────────────────────────────────────

class VantyxHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt: str, *args: Any) -> None:
        log.info(fmt, *args)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _json(self, status: int, body: Any) -> None:
        payload = json.dumps(body, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self._cors()
        self.end_headers()
        self.wfile.write(payload)

    def _html(self, path: Path) -> None:
        if not path.exists():
            self._json(404, {"error": f"File not found: {path.name}"})
            return
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self._cors()
        self.end_headers()
        self.wfile.write(content)

    def _static_file(self, path: Path) -> None:
        if not path.exists():
            self._json(404, {"error": "Not found"})
            return
        mime, _ = mimetypes.guess_type(str(path))
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self._cors()
        self.end_headers()
        self.wfile.write(content)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length > 500_000:
            raise ValueError("Payload too large")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?")[0]

        # Static pages
        if path in _STATIC:
            self._html(_STATIC[path])
            return

        # Assets under vantyx/ directory
        if path.startswith("/vantyx/"):
            self._static_file(_ROOT / path.lstrip("/"))
            return

        # Health
        if path == "/health":
            self._json(200, {"status": "ok", "time": datetime.utcnow().isoformat()})
            return

        # ── API routes ──────────────────────────────────────────────────

        if path == "/api/status":
            self._json(200, self._api_global_status())
            return

        # Marketing
        if path == "/api/marketing/status":
            self._safe_json(lambda: _marketing().status())
            return
        if path == "/api/marketing/posts":
            self._safe_json(lambda: self._marketing_posts())
            return
        if path == "/api/marketing/leads":
            self._safe_json(lambda: self._marketing_leads())
            return
        if path == "/api/marketing/strategy":
            self._safe_json(lambda: self._marketing_strategy())
            return

        # Pricing
        if path == "/api/pricing/status":
            self._safe_json(lambda: _pricing().status())
            return
        if path == "/api/pricing/prices":
            self._safe_json(lambda: _pricing().prices())
            return
        if path == "/api/pricing/alerts":
            self._safe_json(lambda: [self._alert_dict(a) for a in _pricing().alerts()])
            return
        if path == "/api/pricing/analysis":
            self._safe_json(lambda: self._pricing_analysis())
            return

        # Surveillance
        if path == "/api/surveillance/status":
            self._safe_json(lambda: _surveillance().status())
            return
        if path == "/api/surveillance/news":
            self._safe_json(lambda: self._surveillance_news())
            return
        if path == "/api/surveillance/alerts":
            self._safe_json(lambda: [self._surv_alert_dict(a) for a in _surveillance().alerts()])
            return
        if path == "/api/surveillance/report":
            self._safe_json(lambda: self._surveillance_report())
            return

        # CLAUDIA
        if path == "/api/claudia/history":
            self._safe_json(lambda: {"messages": _claudia().history()})
            return

        self._json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        path = self.path.split("?")[0]

        if path == "/submit-loi":
            self._handle_loi()
            return

        if path == "/api/marketing/draft":
            self._safe_post(self._api_marketing_draft)
            return
        if path == "/api/marketing/campaign":
            self._safe_post(self._api_marketing_campaign)
            return
        if path == "/api/marketing/flush-leads":
            self._safe_json(lambda: {"forwarded": _marketing().flush_leads()})
            return
        if path == "/api/marketing/refresh-metrics":
            self._safe_json(lambda: {"updated": _marketing().refresh_metrics()})
            return
        if path == "/api/marketing/analyse":
            self._safe_post(self._api_marketing_analyse)
            return

        if path == "/api/pricing/refresh":
            self._safe_json(lambda: _pricing().refresh())
            return
        if path == "/api/pricing/analyse":
            self._safe_json(lambda: self._pricing_run_analysis())
            return
        if path == "/api/pricing/price":
            self._safe_post(self._api_pricing_add_price)
            return

        if path == "/api/surveillance/scan":
            self._safe_json(lambda: _surveillance().scan())
            return

        # CLAUDIA chat
        if path == "/api/claudia/chat":
            self._safe_post(self._api_claudia_chat)
            return
        if path == "/api/claudia/clear":
            self._safe_json(lambda: (_claudia().clear(), {"ok": True})[1])
            return

        self._json(404, {"error": "Not found"})

    # ── Helpers ────────────────────────────────────────────────────────

    def _safe_json(self, fn) -> None:
        try:
            self._json(200, fn())
        except Exception as exc:
            log.exception("API error")
            self._json(500, {"error": str(exc)})

    def _safe_post(self, fn) -> None:
        try:
            data = self._body()
            self._json(200, fn(data))
        except (json.JSONDecodeError, ValueError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            log.exception("API error")
            self._json(500, {"error": str(exc)})

    def _api_global_status(self) -> dict:
        status: dict[str, Any] = {"time": datetime.utcnow().isoformat()}
        try:
            status["marketing"] = _marketing().status()
        except Exception as e:
            status["marketing"] = {"error": str(e)}
        try:
            status["pricing"] = _pricing().status()
        except Exception as e:
            status["pricing"] = {"error": str(e)}
        try:
            status["surveillance"] = _surveillance().status()
        except Exception as e:
            status["surveillance"] = {"error": str(e)}
        return status

    def _marketing_posts(self) -> list:
        from agents.marketing.storage import get_posts
        from agents.marketing.models import PostStatus
        posts = get_posts(limit=20)
        return [
            {
                "id": p.id,
                "platform": p.platform.value,
                "content": p.content[:120],
                "hashtags": p.hashtags,
                "status": p.status.value,
                "scheduled_at": p.scheduled_at.isoformat() if p.scheduled_at else None,
                "published_at": p.published_at.isoformat() if p.published_at else None,
            }
            for p in posts
        ]

    def _marketing_leads(self) -> list:
        from agents.marketing.storage import get_leads
        leads = get_leads(limit=20)
        return [
            {
                "id": l.id,
                "source": l.source,
                "name": l.name,
                "company": l.company,
                "product_interest": l.product_interest,
                "quantity_mt": l.quantity_mt,
                "forwarded": l.forwarded,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in leads
        ]

    def _marketing_strategy(self) -> dict:
        insight = _marketing().insight_history()
        if not insight:
            return {"available": False}
        i = insight[0]
        return {
            "available": True,
            "id": i.id,
            "generated_at": i.generated_at.isoformat(),
            "posts_analysed": i.posts_analysed,
            "summary": i.summary,
            "recommendations": i.recommendations,
            "best_platform": i.best_platform,
            "best_tone": i.best_tone,
            "top_hashtags": i.top_hashtags,
        }

    def _pricing_analysis(self) -> dict:
        a = _pricing().analysis()
        if not a:
            return {"available": False}
        return {
            "available": True,
            "generated_at": a.generated_at.isoformat(),
            "market_summary": a.market_summary,
            "recommendations": a.recommendations,
            "buying_opportunities": a.buying_opportunities,
            "risk_warnings": a.risk_warnings,
            "outlook": a.outlook,
        }

    def _pricing_run_analysis(self) -> dict:
        a = _pricing().analyse(force=True)
        if not a:
            return {"ok": False, "message": "No price data available"}
        return {"ok": True, "outlook": a.outlook, "recommendations": a.recommendations}

    def _surveillance_news(self) -> list:
        items = _surveillance().news(limit=20)
        return [
            {
                "id": i.id,
                "title": i.title,
                "url": i.url,
                "source": i.source,
                "published_at": i.published_at.isoformat() if i.published_at else None,
                "summary": i.summary,
                "relevance": i.relevance.value,
                "sentiment": i.sentiment.value,
                "tags": i.tags,
            }
            for i in items
        ]

    def _surveillance_report(self) -> dict:
        r = _surveillance().report()
        if not r:
            return {"available": False}
        return {
            "available": True,
            "id": r.id,
            "generated_at": r.generated_at.isoformat(),
            "items_analysed": r.items_analysed,
            "executive_summary": r.executive_summary,
            "opportunities": r.opportunities,
            "threats": r.threats,
            "key_trends": r.key_trends,
            "action_items": r.action_items,
        }

    def _alert_dict(self, a) -> dict:
        return {
            "id": a.id, "product": a.product, "alert_type": a.alert_type,
            "severity": a.severity.value, "message": a.message,
            "price_usd_mt": a.price_usd_mt, "change_pct": a.change_pct,
            "created_at": a.created_at.isoformat(),
        }

    def _surv_alert_dict(self, a) -> dict:
        return {
            "id": a.id, "alert_type": a.alert_type, "headline": a.headline,
            "detail": a.detail, "sentiment": a.sentiment.value,
            "created_at": a.created_at.isoformat(),
        }

    def _api_marketing_draft(self, data: dict) -> dict:
        from agents.marketing.models import Platform, PostTone
        from datetime import timedelta
        product = data.get("product", "Urea 46%")
        platform = Platform(data.get("platform", "linkedin"))
        tone = PostTone(data.get("tone", "professional"))
        hours = int(data.get("schedule_hours", 0))
        schedule_at = datetime.utcnow() + timedelta(hours=hours) if hours else None
        post = _marketing().draft_post(product=product, platform=platform, tone=tone, schedule_at=schedule_at)
        return {"id": post.id, "status": post.status.value, "content": post.content, "hashtags": post.hashtags}

    def _api_marketing_campaign(self, data: dict) -> dict:
        from agents.marketing.models import Platform
        platforms = [Platform(p) for p in data.get("platforms", ["linkedin", "facebook"])]
        campaign = _marketing().run_campaign(
            name=data.get("name", "New Campaign"),
            product=data.get("product", "Urea 46%"),
            target_audience=data.get("audience", "agricultural buyers globally"),
            platforms=platforms,
            budget_aud=float(data.get("budget", 500)),
            duration_days=int(data.get("days", 30)),
            context=data.get("context"),
        )
        return {"id": campaign.id, "name": campaign.name, "status": campaign.status.value}

    def _api_marketing_analyse(self, data: dict) -> dict:
        force = bool(data.get("force", False))
        insight = _marketing().analyse(force=force)
        if not insight:
            return {"ok": False, "message": "Not enough data. Add force=true or publish more posts."}
        return {"ok": True, "id": insight.id, "recommendations": insight.recommendations}

    def _api_claudia_chat(self, data: dict) -> dict:
        message = (data.get("message") or "").strip()
        if not message:
            raise ValueError("message is required")
        events = _claudia().chat(message)
        return {"events": events}

    def _api_pricing_add_price(self, data: dict) -> dict:
        product = data.get("product")
        price = float(data.get("price_usd_mt", 0))
        notes = data.get("notes", "")
        if not product or price <= 0:
            raise ValueError("product and price_usd_mt are required")
        _pricing().add_price(product, price, notes)
        return {"ok": True}

    def _handle_loi(self) -> None:
        if not _LOI_OK:
            self._json(503, {"error": "LOI handler not available"})
            return
        import smtplib
        length = int(self.headers.get("Content-Length", 0))
        if length > 64_000:
            self._json(413, {"error": "Payload too large"})
            return
        try:
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            self._json(400, {"error": f"Invalid JSON: {exc}"})
            return
        required = ("fullName", "businessName", "email", "productType",
                    "annualVolume", "deliveryAddress", "primaryApplication", "deliverySchedule")
        missing = [f for f in required if not str(data.get(f, "")).strip()]
        if missing:
            self._json(422, {"error": f"Missing fields: {', '.join(missing)}"})
            return
        try:
            send_loi_email(data)
        except RuntimeError as exc:
            self._json(503, {"error": str(exc)})
            return
        except smtplib.SMTPException as exc:
            self._json(502, {"error": f"Email delivery failed: {exc}"})
            return
        self._json(200, {"ok": True, "message": "LOI submitted successfully."})


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def main() -> None:
    host = os.environ.get("LOI_HOST", "0.0.0.0")
    port = int(os.environ.get("LOI_PORT", "8080"))

    # Pre-initialise agents so first request is fast
    try:
        _marketing()
        log.info("Marketing agent initialised")
    except Exception as e:
        log.warning("Marketing agent init failed: %s", e)
    try:
        _pricing()
        log.info("Pricing agent initialised")
    except Exception as e:
        log.warning("Pricing agent init failed: %s", e)
    try:
        _surveillance()
        log.info("Surveillance agent initialised")
    except Exception as e:
        log.warning("Surveillance agent init failed: %s", e)

    # Start marketing scheduler in background
    try:
        _marketing().start(scheduler_poll=60)
    except Exception as e:
        log.warning("Marketing scheduler start failed: %s", e)

    log.info("=" * 55)
    log.info("  Vantyx Local Server starting on port %d", port)
    log.info("  Website:   http://localhost:%d/", port)
    log.info("  LOI Form:  http://localhost:%d/loi", port)
    log.info("  Dashboard: http://localhost:%d/dashboard", port)
    log.info("=" * 55)

    server = ThreadedHTTPServer((host, port), VantyxHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
