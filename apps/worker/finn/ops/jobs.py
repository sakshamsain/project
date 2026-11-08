"""Scheduled jobs, written against any NSE client so they run on Modal and in tests.

    poll      every few minutes: today's filings (and yesterday's tail after midnight)
    eod       weekday evenings: bars, index closes, ex-dates, calendar, anomalies
    backfill  once: N days of filings and bars, then anomalies and reactions per day
    seed      reference data: companies, symbols, the demo profile

Each step runs in its own transaction, so a failure loses one step, not the run.
Source health is recorded per feed for the status page.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from functools import partial
from typing import Any, Protocol

from finn.core.db import Conn, connect, fetch_all
from finn.ops.seed import seed_companies, seed_demo_profile
from finn.push import eod
from finn.push.pipeline import ingest_announcements, rescore_recent
from finn.sources.nse import (
    IST,
    parse_board_meetings,
    parse_corporate_actions,
    parse_delivery_file,
    parse_equity_master,
    parse_index_closes,
    trading_days_back,
)

log = logging.getLogger("finn.jobs")


class Nse(Protocol):
    def announcements(
        self, day_from: date, day_to: date, symbol: str | None = None
    ) -> list[Any]: ...
    def board_meetings(self, day_from: date, day_to: date) -> list[Any]: ...
    def corporate_actions(self, day_from: date, day_to: date) -> list[Any]: ...
    def equity_master(self) -> str: ...
    def delivery_file(self, day: date) -> str | None: ...
    def index_closes(self, day: date) -> str | None: ...


def now_ist() -> datetime:
    return datetime.now(IST)


@contextmanager
def _step(url: str) -> Iterator[Conn]:
    with connect(url) as conn:
        yield conn


def record_health(url: str, source: str, ok: bool, error: str | None = None) -> None:
    with _step(url) as conn:
        if ok:
            fetch_all(
                conn,
                "insert into source_health (source, last_ok_at, consecutive_failures)"
                " values (%s, now(), 0) on conflict (source) do update"
                " set last_ok_at = now(), consecutive_failures = 0",
                [source],
            )
        else:
            fetch_all(
                conn,
                "insert into source_health"
                " (source, last_error_at, last_error, consecutive_failures)"
                " values (%s, now(), %s, 1) on conflict (source) do update"
                " set last_error_at = now(), last_error = excluded.last_error,"
                " consecutive_failures = source_health.consecutive_failures + 1",
                [source, (error or "")[:500]],
            )


def _watched[T](url: str, source: str, fn: Callable[[], T]) -> T:
    try:
        out = fn()
    except Exception as exc:
        record_health(url, source, False, f"{type(exc).__name__}: {exc}")
        raise
    record_health(url, source, True)
    return out


def run_seed(url: str, nse: Nse) -> dict[str, Any]:
    text = _watched(url, "nse_equity_master", nse.equity_master)
    equities = parse_equity_master(text)
    with _step(url) as conn:
        n = seed_companies(conn, equities)
        missing = seed_demo_profile(conn)
    return {"companies": n, "demo_missing": missing}


def run_poll(url: str, nse: Nse, at: datetime | None = None) -> dict[str, Any]:
    at = at or now_ist()
    days = [at.date()]
    if at.hour < 2:
        days.insert(0, at.date() - timedelta(days=1))
    out: dict[str, Any] = {}
    for d in days:
        rows = _watched(url, "nse_announcements", partial(nse.announcements, d, d))
        with _step(url) as conn:
            out[d.isoformat()] = ingest_announcements(conn, rows).as_dict()
    return out


def run_eod(url: str, nse: Nse, day: date | None = None, force: bool = False) -> dict[str, Any]:
    """Idempotent; scheduled several times an evening until the delivery file appears."""
    d = day or now_ist().date()
    if d.weekday() >= 5:
        return {"skipped": "weekend"}
    if not force:
        with _step(url) as conn:
            done = fetch_all(
                conn, "select 1 from anomalies where trade_date = %s limit 1", [d]
            ) or fetch_all(
                conn,
                "select 1 from source_health where source = 'eod_done' and last_ok_at::date = %s",
                [d],
            )
        if done:
            return {"skipped": "already done"}
    text = _watched(url, "nse_delivery_file", lambda: nse.delivery_file(d))
    if text is None:
        return {"skipped": "delivery file not published (holiday or too early)"}
    bars = parse_delivery_file(text)
    idx_text = _watched(url, "nse_index_closes", lambda: nse.index_closes(d))
    actions = parse_corporate_actions(
        _watched(url, "nse_corporate_actions", lambda: nse.corporate_actions(d, d + timedelta(30)))
    )
    meetings = parse_board_meetings(
        _watched(url, "nse_board_meetings", lambda: nse.board_meetings(d, d + timedelta(30)))
    )
    with _step(url) as conn:
        stored = eod.store_bars(conn, bars)
        if idx_text:
            eod.store_index(conn, parse_index_closes(idx_text))
        eod.store_corporate_actions(conn, actions)
        eod.store_board_meetings(conn, meetings)
    with _step(url) as conn:
        report = eod.link_and_react(conn, eod.detect_anomalies(conn, d))
    record_health(url, "eod_done", True)
    return {"bars": stored, **report.as_dict()}


def run_backfill(
    url: str,
    nse: Nse,
    filing_days: int = 60,
    price_days: int = 90,
    end: date | None = None,
    pause_s: float = 0.0,
) -> dict[str, Any]:
    """Bars first (anomalies need history), then filings, then anomalies and reactions
    for every session that has both."""
    end = end or now_ist().date()
    summary: dict[str, Any] = {"bars": 0, "filings": 0, "sessions": 0, "holidays": []}

    sessions: list[date] = []
    for d in trading_days_back(end, price_days * 5 // 7):
        text = nse.delivery_file(d)
        if text is None:
            summary["holidays"].append(d.isoformat())
            continue
        idx = nse.index_closes(d)
        with _step(url) as conn:
            summary["bars"] += eod.store_bars(conn, parse_delivery_file(text))
            if idx:
                eod.store_index(conn, parse_index_closes(idx))
        sessions.append(d)
        time.sleep(pause_s)

    start = end - timedelta(days=price_days)
    with _step(url) as conn:
        eod.store_corporate_actions(
            conn, parse_corporate_actions(nse.corporate_actions(start, end + timedelta(30)))
        )
        eod.store_board_meetings(
            conn, parse_board_meetings(nse.board_meetings(end, end + timedelta(30)))
        )

    for i in range(filing_days, -1, -1):
        d = end - timedelta(days=i)
        rows = nse.announcements(d, d)
        with _step(url) as conn:
            summary["filings"] += ingest_announcements(conn, rows).new_filings
        time.sleep(pause_s)

    lookback_start = end - timedelta(days=filing_days)
    for d in sessions:
        if d < lookback_start:
            continue
        with _step(url) as conn:
            eod.link_and_react(conn, eod.detect_anomalies(conn, d))
        summary["sessions"] += 1
    return summary


def run_rescan(url: str, sessions: int = 40, end: date | None = None) -> dict[str, Any]:
    """Recompute anomalies, links and reactions for the last `sessions` stored sessions,
    after a change to the rules or the floors."""
    with _step(url) as conn:
        days = [
            r["trade_date"]
            for r in fetch_all(
                conn,
                "select distinct trade_date from eod_prices where trade_date <= %s"
                " order by trade_date desc limit %s",
                [end or now_ist().date(), sessions],
            )
        ]
    with _step(url) as conn:
        rescored_all = rescore_recent(conn, days=max(60, sessions * 2))
    totals = {"sessions": 0, "anomalies": 0, "linked": 0, "events_rescored": rescored_all}
    for d in sorted(days):
        with _step(url) as conn:
            r = eod.link_and_react(conn, eod.detect_anomalies(conn, d))
        totals["sessions"] += 1
        totals["anomalies"] += r.anomalies
        totals["linked"] += r.linked
        totals["events_rescored"] += r.events_rescored
    return totals


def run_rebuild(url: str, rescan_sessions: int = 45) -> dict[str, Any]:
    """Re-read every filing with the current rules, rebuild events, then restore anomaly
    links and reactions. Safe to run while polls are paused by the advisory lock."""
    from finn.push.rebuild import detach_all, filing_days, reclassify, recluster_day

    with _step(url) as conn:
        changed = reclassify(conn)
    with _step(url) as conn:
        dropped = detach_all(conn)
        days = filing_days(conn)
    events = 0
    for d in days:
        with _step(url) as conn:
            events += recluster_day(conn, d)
    rescan = run_rescan(url, rescan_sessions)
    return {
        "reclassified": changed,
        "events_dropped": dropped,
        "days": len(days),
        "events_written": events,
        "rescan": rescan,
    }
