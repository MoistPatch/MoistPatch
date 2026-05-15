"""CurrencyAgent — live FX rates, history, alerts, sparklines."""
from __future__ import annotations

from datetime import datetime, timedelta

from .fetcher import fetch_live_rates
from .storage import (
    deactivate_alert,
    delete_alert,
    get_active_alerts,
    get_alert_history,
    get_daily_rates,
    get_latest_rates,
    get_rate_at,
    get_rate_history,
    init_db,
    save_alert,
    save_alert_trigger,
    save_snapshots,
    snapshot_count,
)


class CurrencyAgent:

    def __init__(self) -> None:
        init_db()

    # ── Core ────────────────────────────────────────────────────────────

    def refresh(self) -> dict:
        """Fetch live rates, persist snapshot, check alerts. Returns summary."""
        data = fetch_live_rates()
        rates = data["rates"]
        save_snapshots(rates)
        triggered = self._check_alerts(rates)
        return {
            "currencies_fetched": len(rates),
            "fetched_at": data["fetched_at"],
            "alerts_triggered": triggered,
        }

    def _check_alerts(self, rates: dict[str, float]) -> int:
        triggered = 0
        for alert in get_active_alerts():
            code = alert["currency_code"]
            rate = rates.get(code)
            if rate is None:
                continue
            hit = (
                (alert["condition"] == "above" and rate >= alert["threshold"])
                or (alert["condition"] == "below" and rate <= alert["threshold"])
            )
            if hit:
                save_alert_trigger(code, rate, alert["threshold"], alert["condition"])
                deactivate_alert(alert["id"])
                triggered += 1
        return triggered

    # ── Rates & history ─────────────────────────────────────────────────

    def rates(self, codes: list[str] | None = None) -> dict:
        """Current rates with 1h / 24h percentage changes and 7-day sparklines."""
        latest = get_latest_rates()
        now = datetime.utcnow()
        result: dict[str, dict] = {}

        for code, info in latest.items():
            if codes and code not in codes:
                continue
            rate = info["rate"]
            r1h = get_rate_at(code, now - timedelta(hours=1))
            r24h = get_rate_at(code, now - timedelta(hours=24))
            sparkline = get_daily_rates(code, days=7)

            result[code] = {
                "code": code,
                "rate": rate,
                "fetched_at": info["fetched_at"],
                "change_1h": round((rate - r1h) / r1h * 100, 4) if r1h else None,
                "change_24h": round((rate - r24h) / r24h * 100, 4) if r24h else None,
                "sparkline": [round(v, 6) for v in sparkline],
            }

        return result

    def history(self, code: str, days: int = 30) -> list[dict]:
        return get_rate_history(code.upper(), days)

    # ── Alerts ──────────────────────────────────────────────────────────

    def set_alert(self, code: str, condition: str, threshold: float) -> int:
        if condition not in ("above", "below"):
            raise ValueError("condition must be 'above' or 'below'")
        return save_alert(code.upper(), condition, threshold)

    def get_alerts(self) -> list[dict]:
        return get_active_alerts()

    def remove_alert(self, alert_id: int) -> None:
        delete_alert(alert_id)

    def alert_history(self, limit: int = 20) -> list[dict]:
        return get_alert_history(limit)

    # ── Status ──────────────────────────────────────────────────────────

    def status(self) -> dict:
        latest = get_latest_rates()
        return {
            "currencies_tracked": len(latest),
            "active_alerts": len(get_active_alerts()),
            "snapshots_stored": snapshot_count(),
        }
