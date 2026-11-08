"""The write path end to end on a real Postgres, with recorded NSE rows."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from finn.core.db import connect, fetch_all
from finn.ops.seed import DEMO_PROFILE_ID, seed_companies, seed_demo_profile
from finn.push import eod
from finn.push.pipeline import ingest_announcements
from finn.sources.nse import IST, DailyBar, IndexClose, parse_equity_master, trading_days_back

NSE = Path(__file__).resolve().parents[3] / "fixtures" / "nse"


def _rows(name: str) -> list[dict[str, Any]]:
    data = json.loads((NSE / name).read_text())
    assert isinstance(data, list)
    return data


def _seed(url: str) -> None:
    with connect(url) as conn:
        seed_companies(conn, parse_equity_master((NSE / "EQUITY_L_sample.csv").read_text()))
        seed_demo_profile(conn)


def test_ingest_is_idempotent_and_clusters(clean_db: str) -> None:
    _seed(clean_db)
    rows = _rows("announcements_TATAPOWER_30d.json") + _rows("announcements_market_1d_sample.json")
    with connect(clean_db) as conn:
        first = ingest_announcements(conn, rows)
    assert first.new_filings == len({r["seq_id"] for r in rows})
    assert first.new_companies > 0  # symbols outside the sample master get companies

    with connect(clean_db) as conn:
        again = ingest_announcements(conn, rows)
        events = fetch_all(conn, "select count(*) as n from events")[0]["n"]
        unlinked = fetch_all(conn, "select count(*) as n from filings where event_id is null")
        exits = fetch_all(
            conn,
            "select e.filing_count, e.family, e.tier from events e"
            " join company_aliases a on a.isin = e.isin and a.value = 'TATAPOWER'"
            " where e.family = 'management_change'",
        )
        tata_isin = fetch_all(conn, "select distinct isin from filings where symbol = 'TATAPOWER'")
    assert again.new_filings == 0
    assert unlinked[0]["n"] == 0
    assert events < first.new_filings  # clustering merged some filings
    assert [e["filing_count"] for e in exits] == [3]  # three directors, one event
    assert [r["isin"] for r in tata_isin] == ["INE245A01021"]  # canonical, not the legacy ISIN


def test_brief_assigns_tiers_with_the_front_cap(clean_db: str) -> None:
    _seed(clean_db)
    rows = _rows("announcements_TATAPOWER_30d.json") + _rows("announcements_market_1d_sample.json")
    with connect(clean_db) as conn:
        ingest_announcements(conn, rows)
        brief = fetch_all(
            conn,
            "select * from brief(%s, %s, %s)",
            [DEMO_PROFILE_ID, datetime(2026, 10, 1, tzinfo=IST), datetime(2026, 11, 9, tzinfo=IST)],
        )
    assert brief
    assert {r["symbol"] for r in brief} <= {
        "TATAPOWER",
        "HDFCBANK",
        "HCLTECH",
        "SBIN",
        "SUNPHARMA",
        "LT",
        "ETERNAL",
    }
    tiers = [r["tier"] for r in brief]
    assert set(tiers) <= {"front", "oneliner", "folded"}
    assert tiers.count("front") <= 5
    scores = [r["score"] for r in brief]
    assert scores == sorted(scores, reverse=True)
    for r in brief:
        if r["tier"] == "front":
            assert r["score"] >= 0.75
        if r["tier"] == "folded":
            assert r["score"] < 0.35


def _bars(symbol: str, days: list[date], spike: bool) -> list[DailyBar]:
    out = []
    close = 350.0
    for i, d in enumerate(days):
        last = i == len(days) - 1
        prev = close
        close = prev * (0.94 if (last and spike) else (1.002 if i % 2 else 0.998))
        out.append(
            DailyBar(
                symbol=symbol,
                series="EQ",
                trade_date=d,
                prev_close=prev,
                open=prev,
                high=max(prev, close),
                low=min(prev, close),
                close=round(close, 2),
                volume=3_000_000 if (last and spike) else 1_000_000 + (i % 3) * 10_000,
                turnover_cr=None,
                trades=None,
                delivery_qty=None,
                delivery_pct=45.0,
            )
        )
    return out


def test_eod_finds_the_move_links_the_filing_and_rescores(clean_db: str) -> None:
    _seed(clean_db)
    with connect(clean_db) as conn:
        ingest_announcements(conn, _rows("announcements_TATAPOWER_30d.json"))
        before = fetch_all(
            conn,
            "select id, score, category from events where headline like %s",
            ["%Singapore Court%"],
        )
    assert len(before) == 1 and before[0]["category"] == "litigation"

    days = trading_days_back(date(2026, 11, 9), 25)
    with connect(clean_db) as conn:
        eod.store_bars(conn, _bars("TATAPOWER", days, spike=True) + _bars("HCLTECH", days, False))
        for d in days:
            eod.store_index(conn, {"NIFTY 50": IndexClose("NIFTY 50", d, 25000.0, 0.0)})
    with connect(clean_db) as conn:
        report = eod.link_and_react(conn, eod.detect_anomalies(conn, date(2026, 11, 9)))
        hits = fetch_all(
            conn,
            "select a.kind, a.linked_event_id from anomalies a"
            " join company_aliases c on c.isin = a.isin and c.value = 'TATAPOWER'",
        )
        after = fetch_all(
            conn, "select score, enrichment from events where id = %s", [before[0]["id"]]
        )
    kinds = {h["kind"] for h in hits}
    assert {"volume_multiple", "price_move"} <= kinds
    assert all(h["linked_event_id"] == before[0]["id"] for h in hits)
    assert report.stocks == 2 and report.linked == len(hits)
    reaction = after[0]["enrichment"]["reaction"]
    assert reaction["trade_date"] == "2026-11-09"
    assert reaction["abnormal_return_pct"] < -5.9
    assert after[0]["score"] > before[0]["score"]


def test_mechanical_ex_date_mutes_price_rules(clean_db: str) -> None:
    _seed(clean_db)
    days = trading_days_back(date(2026, 11, 9), 25)
    with connect(clean_db) as conn:
        eod.store_bars(conn, _bars("TATAPOWER", days, spike=True))
        isin = fetch_all(conn, "select isin from company_aliases where value = 'TATAPOWER'")[0][
            "isin"
        ]
        fetch_all(
            conn,
            "insert into corporate_actions (isin, ex_date, subject, kind) values (%s, %s, %s, %s)",
            [isin, date(2026, 11, 9), "Bonus 1:1", "bonus"],
        )
    with connect(clean_db) as conn:
        report = eod.detect_anomalies(conn, date(2026, 11, 9))
        kinds = {r["kind"] for r in fetch_all(conn, "select kind from anomalies")}
    assert report.muted == 1
    assert kinds == {"volume_multiple"}


def test_session_window_puts_saturday_filings_on_monday() -> None:
    from finn.push.pipeline import session_bounds

    start, end = session_bounds(date(2026, 11, 6), date(2026, 11, 9))
    saturday_filing = datetime(2026, 11, 7, 18, 40, tzinfo=IST)
    assert start < saturday_filing <= end
    assert end - start == timedelta(days=3)


def test_rebuild_reproduces_live_clustering(clean_db: str) -> None:
    from finn.push.rebuild import detach_all, filing_days, reclassify, recluster_day

    _seed(clean_db)
    rows = _rows("announcements_TATAPOWER_30d.json") + _rows("announcements_market_1d_sample.json")
    with connect(clean_db) as conn:
        ingest_announcements(conn, rows)
        live = fetch_all(
            conn, "select cluster_key, filing_count, score from events order by cluster_key"
        )
    with connect(clean_db) as conn:
        assert reclassify(conn) == 0  # same rules, nothing to change
        assert detach_all(conn) == len(live)
        for d in filing_days(conn):
            recluster_day(conn, d)
        rebuilt = fetch_all(
            conn, "select cluster_key, filing_count, score from events order by cluster_key"
        )
        unlinked = fetch_all(conn, "select count(*) as n from filings where event_id is null")
    assert [(r["cluster_key"], r["filing_count"]) for r in rebuilt] == [
        (r["cluster_key"], r["filing_count"]) for r in live
    ]
    assert unlinked[0]["n"] == 0


def test_front_page_event_notifies_once(clean_db: str, monkeypatch: object) -> None:
    import pywebpush

    from finn.push import notify

    sent: list[dict[str, object]] = []

    def fake_webpush(**kwargs: object) -> None:
        sent.append(kwargs)

    monkeypatch.setattr(pywebpush, "webpush", fake_webpush)  # type: ignore[attr-defined]
    _seed(clean_db)
    rows = _rows("announcements_TATAPOWER_30d.json")
    with connect(clean_db) as conn:
        ingest_announcements(conn, rows)
        fetch_all(
            conn,
            "insert into push_subscriptions (profile_id, endpoint, p256dh, auth)"
            " values (%s, 'https://fcm.googleapis.com/fcm/send/x', 'k', 'a')",
            [DEMO_PROFILE_ID],
        )
        fetch_all(
            conn,
            "update events set tier = 'front' where headline like %s",
            ["%Singapore Court%"],
        )
    now = datetime(2026, 11, 7, 20, 0, tzinfo=IST)
    with connect(clean_db) as conn:
        assert notify.queue_event_notifications(conn, now) == 1
        assert notify.queue_event_notifications(conn, now) == 0  # deduped
        result = notify.send_pending(conn, "unused-key", "mailto:test@example.com")
    assert result == {"sent": 1, "failed": 0, "gone": 0}
    payload = json.loads(str(sent[0]["data"]))
    assert payload["title"] == "TATAPOWER: Legal or regulatory"
    assert payload["url"].startswith("/event/")


def test_quiet_hours_hold_then_release(clean_db: str) -> None:
    from finn.push import notify

    _seed(clean_db)
    with connect(clean_db) as conn:
        ingest_announcements(conn, _rows("announcements_TATAPOWER_30d.json"))
        fetch_all(
            conn,
            "insert into push_subscriptions (profile_id, endpoint, p256dh, auth)"
            " values (%s, 'https://fcm.googleapis.com/fcm/send/y', 'k', 'a')",
            [DEMO_PROFILE_ID],
        )
        fetch_all(
            conn,
            "update events set tier = 'front', first_seen_at = %s where headline like %s",
            [datetime(2026, 11, 7, 22, 30, tzinfo=IST), "%Singapore%"],
        )
        night = datetime(2026, 11, 7, 23, 0, tzinfo=IST)
        assert notify.queue_event_notifications(conn, night) == 1
        assert notify.release_held(conn, night) == 0
        morning = datetime(2026, 11, 8, 7, 5, tzinfo=IST)
        assert notify.release_held(conn, morning) == 1
        status = fetch_all(conn, "select status from notifications")
    assert [r["status"] for r in status] == ["queued"]
