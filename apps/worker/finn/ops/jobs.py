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
    if hasattr(nse, "integrated_filings"):
        out["results"] = run_results(url, nse, days=10, limit=4)
        out["people"] = run_people(url, nse, make_llm(url), days=10, limit=3)
        from finn.ops.research_jobs import claim, run_job

        job = claim(url)
        if job is not None:
            out["research"] = run_job(url, nse, make_llm(url), job)
    out["notify"] = run_notify(url, at)
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
    return {"bars": stored, **report.as_dict(), "notify": run_notify(url, trade_date=d)}


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


def run_rebuild(url: str, rescan_sessions: int = 45, nse: Any = None) -> dict[str, Any]:
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
    cards = run_results(url, nse, days=90, limit=200, force=True) if nse is not None else None
    return {
        "reclassified": changed,
        "events_dropped": dropped,
        "days": len(days),
        "events_written": events,
        "rescan": rescan,
        "results_cards": cards,
    }


def run_results(
    url: str, nse: Any, days: int = 10, limit: int = 8, force: bool = False
) -> dict[str, Any]:
    """Build results cards for recent results events on held companies."""
    from finn.push.results import (
        build_results_card,
        due,
        last_quarter_end_before,
        pending_results_events,
        store_card,
    )

    now = now_ist()
    with _step(url) as conn:
        todo = [
            e
            for e in pending_results_events(conn, days, limit, force)
            if force or due(e["attempted_at"], now)
        ]
    statuses: dict[str, int] = {}
    for e in todo:
        quarter = last_quarter_end_before(e["first_seen_at"].astimezone(IST).date())
        try:
            card = build_results_card(nse, str(e["symbol"]), quarter)
        except Exception as exc:  # one company's bad file must not stop the rest
            card = {"status": "error", "reason": f"{type(exc).__name__}: {exc}"[:300]}
        with _step(url) as conn:
            store_card(conn, str(e["isin"]), int(e["id"]), card)
        statuses[card["status"]] = statuses.get(card["status"], 0) + 1
        if card["status"] == "ok":
            # The bridge: these results checked against the company's Promise Ledger.
            from finn.pull.bridge import recheck_after_results

            try:
                summary = recheck_after_results(
                    url, nse, str(e["isin"]), str(e["symbol"]), int(e["id"])
                )
            except Exception as exc:  # noqa: BLE001 - the card stands without it
                summary = {"error": f"{type(exc).__name__}: {exc}"[:200]}
            if summary is not None:
                statuses["ledger_checked"] = statuses.get("ledger_checked", 0) + 1
    return {"tried": len(todo), "statuses": statuses}


def run_notify(
    url: str, now: datetime | None = None, trade_date: date | None = None
) -> dict[str, Any]:
    """Queue and send web push: front-page events, and the EOD summary when given a date."""
    import os

    from finn.push.notify import (
        queue_eod_notifications,
        queue_event_notifications,
        release_held,
        send_pending,
    )

    key, subject = os.environ.get("VAPID_PRIVATE_KEY"), os.environ.get("VAPID_SUBJECT")
    if not key or not subject:
        return {"skipped": "VAPID keys not set"}
    now = now or now_ist()
    with _step(url) as conn:
        queued = queue_event_notifications(conn, now)
        if trade_date is not None:
            queued += queue_eod_notifications(conn, trade_date, now)
        released = release_held(conn, now)
    with _step(url) as conn:
        sent = send_pending(conn, key, subject)
    return {"queued": queued, "released": released, **sent}


def make_llm(url: str) -> Any:
    import os

    from finn.llm.client import DbStore, Llm

    return Llm(os.environ.get("GEMINI_API_KEY"), os.environ.get("GROQ_API_KEY"), DbStore(url))


def run_people(url: str, nse: Any, llm: Any, days: int = 30, limit: int = 6) -> dict[str, Any]:
    """People cards for board and management changes on held companies."""
    from finn.core.db import Jsonb
    from finn.push.people import (
        card_json,
        event_attachments,
        extract_people,
        merge_cards,
        pending_people_events,
    )
    from finn.push.results import due
    from finn.sources.pdf import NotAPdf, pdf_text

    now = now_ist()
    with _step(url) as conn:
        todo = [e for e in pending_people_events(conn, days, limit) if due(e["attempted_at"], now)]
        urls = {int(e["id"]): event_attachments(conn, int(e["id"])) for e in todo}
    statuses: dict[str, int] = {}
    for e in todo:
        cards: list[dict[str, Any]] = []
        status = "empty"
        try:
            for u in urls[int(e["id"])]:
                data = nse.fetch_bytes(u)
                if data is None:
                    continue
                try:
                    text = pdf_text(data)
                except NotAPdf:
                    continue
                if text.scanned:
                    status = "scanned"
                    continue
                cards.append(card_json(extract_people(llm, text.pages, str(e["company"])), u))
            card = merge_cards(cards) if cards else {"status": status, "people": []}
        except Exception as exc:  # one bad filing must not stop the rest
            card = {"status": "error", "reason": f"{type(exc).__name__}: {exc}"[:300]}
        card["attempted_at"] = now.isoformat()
        with _step(url) as conn:
            fetch_all(
                conn,
                "update events set enrichment = jsonb_set(enrichment, '{people_card}', %s)"
                " where id = %s",
                [Jsonb(card), int(e["id"])],
            )
        st = str(card["status"])
        statuses[st] = statuses.get(st, 0) + 1
    return {"tried": len(todo), "statuses": statuses}


def tracked_companies(url: str) -> list[dict[str, Any]]:
    """Companies someone follows: any profile's holdings, and every company with a ledger."""
    with _step(url) as conn:
        return fetch_all(
            conn,
            "select distinct a.isin, a.value as symbol from company_aliases a"
            " where a.kind = 'nse_symbol' and a.valid_to is null and a.isin in ("
            "   select isin from holdings union"
            "   select isin from dossier_sections where section = 'ledger')",
        )


def stale_dossiers(url: str, max_age_days: int = 30) -> list[dict[str, Any]]:
    """Tracked companies whose dossier is missing, lacks the annual reports, is older than
    `max_age_days`, or has a results filing, a call transcript or an annual report filed
    since it was built. Everything else is served from what is stored."""
    with _step(url) as conn:
        return fetch_all(
            conn,
            "with t as ("
            "  select distinct a.isin, a.value as symbol from company_aliases a"
            "  where a.kind = 'nse_symbol' and a.valid_to is null and a.isin in ("
            "    select isin from holdings union"
            "    select isin from dossier_sections where section = 'ledger')),"
            " b as (select isin, max(built_at) as built_at from dossier_sections"
            "  where section = 'ledger' group by isin)"
            " select t.isin, t.symbol, b.built_at::text as built_at from t left join b using (isin)"
            " where b.built_at is null"
            "  or b.built_at < now() - make_interval(days => %s)"
            "  or not exists (select 1 from dossier_sections s"
            "                 where s.isin = t.isin and s.section = 'annual_reports')"
            "  or exists (select 1 from filings f where f.isin = t.isin"
            "             and f.filed_at > b.built_at"
            "             and (f.category in ('results', 'earnings_call')"
            "                  or f.subject ilike '%%annual report%%'))"
            " order by b.built_at nulls first, t.symbol",
            [max_age_days],
        )


def run_refresh_dossiers(url: str, nse: Any, llm: Any, limit: int = 40) -> dict[str, Any]:
    """Rebuild stale dossiers one after another. Model answers are cached by input, so a
    rebuild costs calls only for documents filed since the last one."""
    from finn.pull.dossier import build_dossier

    out: dict[str, Any] = {}
    for row in stale_dossiers(url)[:limit]:
        symbol = str(row["symbol"])
        try:
            res = build_dossier(url, nse, llm, symbol)
            annual = res.get("annual", {})
            out[symbol] = {"counts": res.get("counts"), "annual_read": annual.get("read")}
        except Exception as exc:  # noqa: BLE001 - one company must not stop the rest
            out[symbol] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    return out


def run_price_history(url: str, nse: Nse, days: int = 370) -> dict[str, Any]:
    """A year of daily bars for tracked companies, for the charts. Sessions already on
    file for every tracked company are skipped, so re-running only fills gaps."""
    tracked = {str(r["isin"]) for r in tracked_companies(url)}
    end = now_ist().date()
    with _step(url) as conn:
        have = {
            r["trade_date"]
            for r in fetch_all(
                conn,
                "select trade_date from eod_prices where isin = any(%s)"
                " group by trade_date having count(*) >= %s",
                [sorted(tracked), max(1, int(len(tracked) * 0.8))],
            )
        }
    stored = sessions = 0
    for d in trading_days_back(end, days * 5 // 7):
        if d in have:
            continue
        text = nse.delivery_file(d)
        if text is None:
            continue
        with _step(url) as conn:
            isin_of = eod.isins_for(conn, (b.symbol for b in parse_delivery_file(text)))
            bars = [b for b in parse_delivery_file(text) if isin_of.get(b.symbol) in tracked]
            stored += eod.store_bars(conn, bars)
            idx = nse.index_closes(d)
            if idx:
                eod.store_index(conn, parse_index_closes(idx))
        sessions += 1
    return {"tracked": len(tracked), "sessions_added": sessions, "bars": stored}


def run_financials(url: str, nse: Any) -> dict[str, Any]:
    """Up to ten quarters of XBRL figures for every tracked company."""
    from finn.pull.financials import quarterly_results, store_quarters

    done: dict[str, int] = {}
    for r in tracked_companies(url):
        try:
            basis, series = quarterly_results(nse, str(r["symbol"]), quarters=10)
        except Exception as exc:  # one company's bad file must not stop the rest
            log.warning("financials %s: %s", r["symbol"], exc)
            continue
        if basis:
            with _step(url) as conn:
                done[str(r["symbol"])] = store_quarters(conn, str(r["isin"]), basis, series)
    return {"companies": len(done), "quarters": sum(done.values())}
