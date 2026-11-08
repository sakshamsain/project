"""Web push: one notification per front-page event, one end-of-day summary per profile.

Notifications are rows first (`notifications`, unique per profile and dedupe key), so a
retry never sends twice. During quiet hours (22:00 to 07:00 IST) they are held and go out
at the first poll after seven. Only allowlisted push services are ever contacted.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from finn.core.db import Conn, fetch_all
from finn.push.alerts import Limits, StoredHit, limits_from_rules, passes
from finn.sources.nse import IST

QUIET_FROM, QUIET_UNTIL = 22, 7
EVENT_FRESHNESS = timedelta(hours=6)
HELD_EXPIRY = timedelta(hours=12)
PUSH_HOSTS = re.compile(
    r"(^|\.)(fcm\.googleapis\.com|push\.services\.mozilla\.com|push\.apple\.com|"
    r"notify\.windows\.com)$"
)

LABELS = {
    "results": "Results",
    "M&A": "Acquisition or merger",
    "management_change": "Board or management",
    "fund_raise": "Fund raise",
    "pledging": "Promoter pledge",
    "litigation": "Legal or regulatory",
    "capex": "Capacity or capex",
    "credit_rating": "Credit rating",
    "insider_trading": "Insider trade",
    "bonus_split": "Bonus or split",
    "press_release": "Press release",
    "dividend": "Dividend",
}


def in_quiet_hours(now: datetime) -> bool:
    h = now.astimezone(IST).hour
    return h >= QUIET_FROM or h < QUIET_UNTIL


def allowed_endpoint(endpoint: str) -> bool:
    parts = urlsplit(endpoint)
    return parts.scheme == "https" and bool(PUSH_HOSTS.search(parts.hostname or ""))


def queue_event_notifications(conn: Conn, now: datetime) -> int:
    status = "held" if in_quiet_hours(now) else "queued"
    rows = fetch_all(
        conn,
        "insert into notifications (profile_id, dedupe_key, event_id, channel, status)"
        " select distinct h.profile_id, 'event:' || e.id, e.id, 'push', %s"
        " from events e join holdings h on h.isin = e.isin"
        " where e.tier = 'front' and e.first_seen_at >= %s"
        "   and exists (select 1 from push_subscriptions s where s.profile_id = h.profile_id)"
        " on conflict (profile_id, dedupe_key, channel) do nothing returning id",
        [status, now - EVENT_FRESHNESS],
    )
    return len(rows)


def moves_for(
    conn: Conn, profile_id: str, trade_date: date, limits: Limits
) -> list[dict[str, Any]]:
    """Holdings that crossed this profile's limits on one session, biggest move first."""
    rows = fetch_all(
        conn,
        "select a.id, a.isin, a.kind, a.value, a.threshold, a.zscore, al.value as symbol,"
        " ((p.close / nullif(p.prev_close, 0)) - 1) * 100 as return_pct"
        " from anomalies a"
        " join holdings h on h.isin = a.isin and h.profile_id = %s"
        " join company_aliases al on al.isin = a.isin and al.kind = 'nse_symbol'"
        "   and al.valid_to is null"
        " left join eod_prices p on p.isin = a.isin and p.trade_date = a.trade_date"
        " where a.trade_date = %s order by a.isin",
        [profile_id, trade_date],
    )
    by_isin: dict[str, list[Mapping[str, Any]]] = {}
    for r in rows:
        by_isin.setdefault(r["isin"], []).append(r)
    out = []
    for group in by_isin.values():
        hits = [
            StoredHit(r["kind"], float(r["value"]), float(r["threshold"]), _f(r["zscore"]))
            for r in group
        ]
        if any(passes(h, limits, hits) for h in hits):
            first = group[0]
            out.append(
                {
                    "anomaly_id": int(first["id"]),
                    "symbol": first["symbol"],
                    "return_pct": _f(first["return_pct"]),
                    "volume_multiple": next(
                        (h.value for h in hits if h.kind == "volume_multiple"), None
                    ),
                }
            )
    return sorted(out, key=lambda m: -abs(m["return_pct"] or 0.0))


def queue_eod_notifications(conn: Conn, trade_date: date, now: datetime) -> int:
    status = "held" if in_quiet_hours(now) else "queued"
    queued = 0
    for p in fetch_all(conn, "select distinct profile_id from push_subscriptions"):
        pid = str(p["profile_id"])
        rules = fetch_all(
            conn,
            "select kind, (params ->> 'value')::float8 as value from alert_rules"
            " where profile_id = %s and isin is null and enabled",
            [pid],
        )
        moves = moves_for(conn, pid, trade_date, limits_from_rules(rules))
        if not moves:
            continue
        queued += len(
            fetch_all(
                conn,
                "insert into notifications (profile_id, dedupe_key, anomaly_id, channel, status)"
                " values (%s, %s, %s, 'push', %s)"
                " on conflict (profile_id, dedupe_key, channel) do nothing returning id",
                [pid, f"eod:{trade_date.isoformat()}", moves[0]["anomaly_id"], status],
            )
        )
    return queued


def release_held(conn: Conn, now: datetime) -> int:
    if in_quiet_hours(now):
        return 0
    fetch_all(
        conn,
        "update notifications n set status = 'failed' where status = 'held'"
        " and coalesce((select e.first_seen_at from events e where e.id = n.event_id), %s) < %s",
        [now, now - HELD_EXPIRY],
    )
    return len(
        fetch_all(
            conn,
            "update notifications set status = 'queued' where status = 'held' returning id",
        )
    )


def _f(v: Any) -> float | None:
    return None if v is None else float(v)


def _pct(x: float | None) -> str:
    if x is None:
        return ""
    return f"{'−' if x < 0 else '+'}{abs(x):.1f}%"


def payload_for(conn: Conn, n: Mapping[str, Any]) -> dict[str, str] | None:
    if n["event_id"] is not None:
        rows = fetch_all(
            conn,
            "select e.id, e.headline, e.category, al.value as symbol from events e"
            " join company_aliases al on al.isin = e.isin and al.kind = 'nse_symbol'"
            "   and al.valid_to is null where e.id = %s limit 1",
            [n["event_id"]],
        )
        if not rows:
            return None
        e = rows[0]
        return {
            "title": f"{e['symbol']}: {LABELS.get(e['category'], 'Filing')}",
            "body": str(e["headline"] or "New filing"),
            "url": f"/event/{e['id']}",
            "tag": f"event-{e['id']}",
        }
    if n["anomaly_id"] is not None and str(n["dedupe_key"]).startswith("eod:"):
        day = date.fromisoformat(str(n["dedupe_key"])[4:])
        rules = fetch_all(
            conn,
            "select kind, (params ->> 'value')::float8 as value from alert_rules"
            " where profile_id = %s and isin is null and enabled",
            [n["profile_id"]],
        )
        moves = moves_for(conn, str(n["profile_id"]), day, limits_from_rules(rules))
        if not moves:
            return None
        parts = [
            f"{m['symbol']} {_pct(m['return_pct'])}".strip()
            + (f" on {m['volume_multiple']:.1f}× volume" if m["volume_multiple"] else "")
            for m in moves[:4]
        ]
        more = f" and {len(moves) - 4} more" if len(moves) > 4 else ""
        noun = "holding" if len(moves) == 1 else "holdings"
        return {
            "title": f"{len(moves)} {noun} moved past your limits",
            "body": "; ".join(parts) + more,
            "url": "/pulse",
            "tag": f"eod-{day.isoformat()}",
        }
    return None


def send_pending(conn: Conn, private_key: str, subject: str, limit: int = 200) -> dict[str, int]:
    from pywebpush import WebPushException, webpush

    counts = {"sent": 0, "failed": 0, "gone": 0}
    pending = fetch_all(
        conn,
        "select id, profile_id, event_id, anomaly_id, dedupe_key from notifications"
        " where status = 'queued' and channel = 'push' order by id limit %s",
        [limit],
    )
    for n in pending:
        payload = payload_for(conn, n)
        subs = fetch_all(
            conn,
            "select id, endpoint, p256dh, auth from push_subscriptions where profile_id = %s",
            [n["profile_id"]],
        )
        delivered = False
        for s in subs if payload else []:
            if not allowed_endpoint(s["endpoint"]):
                continue
            try:
                webpush(
                    subscription_info={
                        "endpoint": s["endpoint"],
                        "keys": {"p256dh": s["p256dh"], "auth": s["auth"]},
                    },
                    data=json.dumps(payload),
                    vapid_private_key=private_key,
                    vapid_claims={"sub": subject},
                    ttl=12 * 3600,
                    timeout=10,
                )
                delivered = True
            except WebPushException as exc:
                status = getattr(exc.response, "status_code", None)
                if status in (404, 410):  # the browser dropped this subscription
                    fetch_all(conn, "delete from push_subscriptions where id = %s", [s["id"]])
                    counts["gone"] += 1
        fetch_all(
            conn,
            "update notifications set status = %s, sent_at = case when %s then now() end"
            " where id = %s",
            ["sent" if delivered else "failed", delivered, n["id"]],
        )
        counts["sent" if delivered else "failed"] += 1
    return counts
