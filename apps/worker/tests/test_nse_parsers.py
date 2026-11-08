import json
from datetime import date, datetime
from pathlib import Path

from finn.sources.nse import (
    IST,
    is_results_meeting,
    parse_announcement,
    parse_announcements,
    parse_board_meetings,
    parse_corporate_actions,
    parse_date,
    parse_datetime,
    parse_delivery_file,
    parse_equity_master,
    parse_index_closes,
    trading_days_back,
)

NSE = Path(__file__).resolve().parents[3] / "fixtures" / "nse"


def _json(name: str) -> list[dict[str, object]]:
    data = json.loads((NSE / name).read_text())
    assert isinstance(data, list)
    return data


def test_dates_in_every_nse_spelling() -> None:
    assert parse_date("07-Nov-2026") == date(2026, 11, 7)
    assert parse_date("23-JUL-2021") == date(2021, 7, 23)
    assert parse_date("06-11-2026") == date(2026, 11, 6)
    assert parse_date("2026-11-06") == date(2026, 11, 6)
    assert parse_date("-") is None
    assert parse_date("") is None
    assert parse_datetime("07-Nov-2026 18:40:29") == datetime(2026, 11, 7, 18, 40, 29, tzinfo=IST)


def test_announcement_fields_from_a_real_row() -> None:
    rows = _json("announcements_TATAPOWER_30d.json")
    a = parse_announcement(rows[0])
    assert a is not None
    assert a.exchange_id == "106852712"
    assert a.symbol == "TATAPOWER"
    assert a.reported_isin == "INE245A01013"  # superseded ISIN: match by symbol, not this
    assert a.subject == "General Updates"
    assert a.filed_at == datetime(2026, 11, 7, 18, 40, 29, tzinfo=IST)
    assert a.summary and a.summary.startswith("Tata Power Company Limited filed a notice of appeal")
    assert a.attachment_url and a.attachment_url.endswith(".pdf")
    assert a.has_xbrl is True
    assert "Singapore" in a.body


def test_announcements_unescape_entities_and_dedupe() -> None:
    rows = _json("announcements_market_1d_sample.json")
    anns = parse_announcements([*rows, *rows])
    assert len(anns) == len({str(r["seq_id"]) for r in rows})
    assert [a.filed_at for a in anns] == sorted(a.filed_at for a in anns)
    denta = next(a for a in anns if a.symbol == "DENTA")
    assert "₹7,824 Million" in denta.text and "&#8377;" not in denta.text


def test_announcement_without_symbol_is_dropped() -> None:
    assert (
        parse_announcement({"seq_id": "1", "symbol": "", "an_dt": "07-Nov-2026 10:00:00"}) is None
    )
    assert parse_announcement({"seq_id": "1", "symbol": "X", "an_dt": "not a date"}) is None


def test_equity_master() -> None:
    eq = parse_equity_master((NSE / "EQUITY_L_sample.csv").read_text())
    by = {e.symbol: e for e in eq}
    assert by["TATAPOWER"].isin == "INE245A01021"
    assert by["ETERNAL"].listed_on == date(2021, 7, 23)
    assert by["21STCENMGM"].series == "BE"
    assert by["HCLTECH"].face_value == 2.0
    assert len(eq) == 18


def test_delivery_file_keeps_equity_series_only() -> None:
    bars = parse_delivery_file((NSE / "sec_bhavdata_full_06112026_sample.csv").read_text())
    by = {b.symbol: b for b in bars}
    assert "574GS2026" not in by  # government securities are not equities
    e = by["ETERNAL"]
    assert e.trade_date == date(2026, 11, 6)
    assert (e.close, e.prev_close, e.volume) == (363.15, 358.30, 25612265)
    assert e.delivery_qty == 12660903 and e.delivery_pct == 49.43
    assert e.turnover_cr == 917.8353
    t = by["21STCENMGM"]  # trade-for-trade series has no delivery figures
    assert t.series == "BE" and t.delivery_qty is None and t.delivery_pct is None


def test_index_closes_keyed_by_upper_case_name() -> None:
    closes = parse_index_closes((NSE / "ind_close_all_06112026_sample.csv").read_text())
    n50 = closes["NIFTY 50"]
    assert n50.trade_date == date(2026, 11, 6)
    assert n50.close == 25030.35 and n50.change_pct == 2.01
    assert "NIFTY 500" in closes


def test_corporate_actions_equity_only() -> None:
    actions = parse_corporate_actions(_json("corporate_actions_4w_sample.json"))
    assert actions and all(a.series in {"EQ", "BE", "BZ", "SM", "ST"} for a in actions)
    infy = next(a for a in actions if a.symbol == "INFY")
    assert infy.ex_date == date(2026, 11, 3) and "Dividend" in infy.subject
    assert not any(a.symbol == "750GS2056" for a in actions)


def test_board_meetings_merge_duplicate_rows() -> None:
    rows = _json("board_meetings_next_7d.json")
    meetings = parse_board_meetings(rows)
    keys = [(m.symbol, m.meeting_date) for m in meetings]
    assert len(keys) == len(set(keys)) == len({(r["bm_symbol"], r["bm_date"]) for r in rows})
    tp = next(m for m in meetings if m.symbol == "TATAPOWER")
    assert tp.meeting_date == date(2026, 11, 11)
    assert is_results_meeting(tp)


def test_trading_days_back_skips_weekends_and_holidays() -> None:
    days = trading_days_back(date(2026, 11, 9), 3, holidays=[date(2026, 11, 5)])
    assert days == [date(2026, 11, 4), date(2026, 11, 6), date(2026, 11, 9)]
