"""End of day: store bars, find anomalies, tie them to filings, score the reaction.

    delivery file -> eod_prices -> anomalies (finn.push.anomalies) -> linked to the event
    that explains them, or to none ("No filing found") -> event reactions rescored

Bars are stored for every listed equity so a stock added to a portfolio has history from
day one. Anomalies are computed for every stock that traded; the app filters by holdings.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import fmean, pstdev
from typing import Any

from finn.core.db import Conn, copy_upsert, fetch_all
from finn.push.anomalies import Bar, Thresholds, daily_returns_pct, evaluate
from finn.push.corporate_actions import mutes_price_rules, parse_action
from finn.push.pipeline import rescore_events, session_bounds
from finn.sources.nse import BoardMeeting, CorporateAction, DailyBar, IndexClose, is_results_meeting

BENCHMARK = "NIFTY 50"
STORED_INDICES = ("NIFTY 50", "NIFTY 500", "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250")
# Anomalies are stored at these floors; each profile's own thresholds (at or above the
# floors, defaulting to USER_DEFAULTS) filter them at read time, so changing a setting
# never needs a recompute.
FLOOR_THRESHOLDS = Thresholds(
    volume_multiple=1.5, price_move_pct=3.0, sigma=2.0, delivery_multiple=1.3
)
USER_DEFAULTS = Thresholds(delivery_multiple=1.5)


def isins_for(conn: Conn, symbols: Iterable[str]) -> dict[str, str]:
    rows = fetch_all(
        conn,
        "select value, isin from company_aliases"
        " where kind = 'nse_symbol' and value = any(%s) and valid_to is null",
        [sorted(set(symbols))],
    )
    return {r["value"]: r["isin"] for r in rows}


def store_bars(conn: Conn, bars: Sequence[DailyBar], source: str = "bhavcopy") -> int:
    isin_of = isins_for(conn, (b.symbol for b in bars))
    rows = [
        (
            isin_of[b.symbol],
            b.trade_date,
            b.open,
            b.high,
            b.low,
            b.close,
            b.prev_close,
            b.volume,
            b.delivery_qty,
            b.delivery_pct,
            source,
            b.trades,
            b.turnover_cr,
        )
        for b in bars
        if b.symbol in isin_of
    ]
    cols = [
        "isin",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "prev_close",
        "volume",
        "delivery_qty",
        "delivery_pct",
        "source",
        "trades",
        "turnover_cr",
    ]
    copy_upsert(conn, "eod_prices", cols, rows, conflict=["isin", "trade_date"], update=cols[2:])
    return len(rows)


def store_index(conn: Conn, closes: Mapping[str, IndexClose]) -> int:
    rows = [
        (c.name, c.trade_date, c.close, c.change_pct)
        for name, c in closes.items()
        if name in STORED_INDICES
    ]
    copy_upsert(
        conn,
        "index_prices",
        ["index_name", "trade_date", "close", "change_pct"],
        rows,
        conflict=["index_name", "trade_date"],
        update=["close", "change_pct"],
    )
    return len(rows)


def store_corporate_actions(conn: Conn, actions: Sequence[CorporateAction]) -> int:
    isin_of = isins_for(conn, (a.symbol for a in actions))
    rows = []
    for a in actions:
        isin = isin_of.get(a.symbol)
        if isin is None:
            continue
        p = parse_action(a.subject)
        rows.append((isin, a.ex_date, a.subject, a.record_date, p.kind, p.amount_rs))
    copy_upsert(
        conn,
        "corporate_actions",
        ["isin", "ex_date", "subject", "record_date", "kind", "amount_rs"],
        rows,
        conflict=["isin", "ex_date", "subject"],
        update=["record_date", "kind", "amount_rs"],
    )
    return len(rows)


def store_board_meetings(conn: Conn, meetings: Sequence[BoardMeeting]) -> int:
    isin_of = isins_for(conn, (m.symbol for m in meetings))
    rows = [
        (
            isin_of[m.symbol],
            m.meeting_date,
            m.purpose,
            m.description,
            is_results_meeting(m),
            m.announced_at,
        )
        for m in meetings
        if m.symbol in isin_of
    ]
    copy_upsert(
        conn,
        "board_meetings",
        ["isin", "meeting_date", "purpose", "description", "is_results", "announced_at"],
        rows,
        conflict=["isin", "meeting_date"],
        update=["purpose", "description", "is_results", "announced_at"],
    )
    return len(rows)


@dataclass(frozen=True, slots=True)
class Reaction:
    trade_date: date
    return_pct: float | None
    index_return_pct: float | None
    volume_multiple: float | None
    volume_z: float | None

    @property
    def abnormal_return_pct(self) -> float | None:
        if self.return_pct is None:
            return None
        return round(self.return_pct - (self.index_return_pct or 0.0), 4)

    def as_json(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date.isoformat(),
            "return_pct": self.return_pct,
            "index_return_pct": self.index_return_pct,
            "abnormal_return_pct": self.abnormal_return_pct,
            "volume_multiple": self.volume_multiple,
            "volume_z": self.volume_z,
        }


def reaction_of(
    history: Sequence[Bar], index_return_pct: float | None, lookback: int = 20
) -> Reaction:
    """How the last bar moved against its own recent past. Pure."""
    today = history[-1]
    rets = daily_returns_pct([b.close for b in history[-2:]]) if len(history) >= 2 else []
    window = [b.volume for b in history[-(lookback + 1) : -1]]
    multiple = z = None
    if window:
        avg = fmean(window)
        if avg > 0:
            multiple = round(today.volume / avg, 4)
            sd = pstdev(window)
            z = round((today.volume - avg) / sd, 4) if sd > 0 else None
    return Reaction(
        trade_date=date.fromisoformat(today.trade_date),
        return_pct=round(rets[-1], 4) if rets else None,
        index_return_pct=index_return_pct,
        volume_multiple=multiple,
        volume_z=z,
    )


@dataclass(slots=True)
class EodReport:
    trade_date: date
    stocks: int = 0
    anomalies: int = 0
    muted: int = 0
    linked: int = 0
    events_rescored: int = 0
    reactions: dict[str, Reaction] = field(default_factory=dict, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date.isoformat(),
            "stocks": self.stocks,
            "anomalies": self.anomalies,
            "muted": self.muted,
            "linked": self.linked,
            "events_rescored": self.events_rescored,
        }


def detect_anomalies(conn: Conn, trade_date: date, t: Thresholds = FLOOR_THRESHOLDS) -> EodReport:
    report = EodReport(trade_date)
    rows = fetch_all(
        conn,
        "select isin, trade_date, close, volume, delivery_pct, prev_close from ("
        "  select p.*, row_number() over (partition by p.isin order by p.trade_date desc) as rn"
        "  from eod_prices p"
        "  where p.trade_date <= %s and p.trade_date >= %s"
        "    and p.isin in (select isin from eod_prices where trade_date = %s)"
        ") t where rn <= %s order by isin, trade_date",
        [trade_date, trade_date - timedelta(days=60), trade_date, t.lookback + 2],
    )
    bench = fetch_all(
        conn,
        "select trade_date, close from index_prices where index_name = %s"
        " and trade_date <= %s and trade_date >= %s order by trade_date",
        [BENCHMARK, trade_date, trade_date - timedelta(days=60)],
    )
    bench_close = {r["trade_date"]: float(r["close"]) for r in bench}
    muting = fetch_all(
        conn, "select isin, subject from corporate_actions where ex_date = %s", [trade_date]
    )
    subjects: dict[str, list[str]] = {}
    for m in muting:
        subjects.setdefault(m["isin"], []).append(m["subject"])

    series: dict[str, list[Mapping[str, Any]]] = {}
    for r in rows:
        series.setdefault(r["isin"], []).append(r)

    out: list[tuple[Any, ...]] = []
    for isin, bars_raw in series.items():
        bars = [
            Bar(
                trade_date=b["trade_date"].isoformat(),
                close=float(b["close"]),
                volume=int(b["volume"]),
                delivery_pct=None if b["delivery_pct"] is None else float(b["delivery_pct"]),
            )
            for b in bars_raw
            if b["close"] is not None and float(b["close"]) > 0
        ]
        if not bars or bars[-1].trade_date != trade_date.isoformat():
            continue
        report.stocks += 1
        idx_rets = _aligned_index_returns(bars, bench_close)
        prev_close = bars_raw[-1]["prev_close"]
        mute = any(
            mutes_price_rules(s, None if prev_close is None else float(prev_close))
            for s in subjects.get(isin, [])
        )
        report.muted += int(mute)
        hits = evaluate(bars, t, idx_rets, suppress_price_rules=mute)
        report.reactions[isin] = reaction_of(bars, idx_rets[-1] if idx_rets else None, t.lookback)
        for h in hits:
            out.append((isin, trade_date, h.kind, h.value, h.threshold, h.zscore))
    copy_upsert(
        conn,
        "anomalies",
        ["isin", "trade_date", "kind", "value", "threshold", "zscore"],
        out,
        conflict=["isin", "trade_date", "kind"],
        update=["value", "threshold", "zscore"],
    )
    report.anomalies = len(out)
    return report


def _aligned_index_returns(bars: Sequence[Bar], bench_close: Mapping[date, float]) -> list[float]:
    """Benchmark returns on the stock's own dates; empty if any date is missing."""
    closes = [bench_close.get(date.fromisoformat(b.trade_date)) for b in bars]
    if any(c is None for c in closes):
        return []
    return daily_returns_pct([c for c in closes if c is not None])


def link_and_react(conn: Conn, report: EodReport) -> EodReport:
    """Tie each anomaly to the best-scoring event filed during its session, store every
    event's price reaction, and rescore those events."""
    d = report.trade_date
    prev = fetch_all(conn, "select max(trade_date) as d from eod_prices where trade_date < %s", [d])
    prev_day = prev[0]["d"] if prev and prev[0]["d"] else d - timedelta(days=1)
    start, end = session_bounds(prev_day, d)
    events = fetch_all(
        conn,
        "select id, isin, score from events where first_seen_at > %s and first_seen_at <= %s",
        [start, end],
    )
    best: dict[str, int] = {}
    best_score: dict[str, float] = {}
    for e in events:
        s = float(e["score"] or 0.0)
        if e["isin"] not in best or s > best_score[e["isin"]]:
            best[e["isin"]], best_score[e["isin"]] = int(e["id"]), s
    if best:
        linked = fetch_all(
            conn,
            "update anomalies a set linked_event_id = v.event_id"
            " from unnest(%s::text[], %s::bigint[]) as v(isin, event_id)"
            " where a.isin = v.isin and a.trade_date = %s returning a.id",
            [list(best), list(best.values()), d],
        )
        report.linked = len(linked)

    ids: list[int] = []
    payload: list[str] = []
    for e in events:
        r = report.reactions.get(e["isin"])
        if r is not None:
            ids.append(int(e["id"]))
            payload.append(json.dumps(r.as_json()))
    if ids:
        fetch_all(
            conn,
            "update events e set enrichment = jsonb_set(e.enrichment, '{reaction}', v.reaction)"
            " from unnest(%s::bigint[], %s::jsonb[]) as v(id, reaction) where e.id = v.id",
            [ids, payload],
        )
        report.events_rescored = rescore_events(conn, ids)
    return report
