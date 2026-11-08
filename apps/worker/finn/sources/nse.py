"""NSE: parsers for every feed FINN reads, and a polite HTTP client.

Parsers are pure functions over the payloads NSE serves, tested against recorded samples
in `fixtures/nse/`. The client only fetches; it is used from Modal, since NSE does not
answer from every network.

Feeds:
    /api/corporate-announcements   filings, market-wide per day (about 1,200 on a weekday)
    /api/corporate-board-meetings  the results calendar
    /api/corporates-corporateActions  ex-dates that move prices mechanically
    EQUITY_L.csv                   every listed equity with its ISIN
    sec_bhavdata_full_DDMMYYYY.csv daily bars with delivery quantity
    ind_close_all_DDMMYYYY.csv     index closes
"""

from __future__ import annotations

import csv
import html
import io
import re
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30), "IST")

API = "https://www.nseindia.com/api"
HOME = "https://www.nseindia.com/"
ARCHIVES = "https://nsearchives.nseindia.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

# Equity series worth a price bar, best first: EQ is the normal market; BE and BZ are
# trade-for-trade; SM and ST are the SME platform.
EQUITY_SERIES = ("EQ", "BE", "BZ", "SM", "ST")

_DATE_FORMATS = ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y")


def parse_date(text: str | None) -> date | None:
    """NSE writes dates as 07-Nov-2026, 07-NOV-2026, 07-11-2026 or 2026-11-07."""
    if not text:
        return None
    s = text.strip()
    if not s or s == "-":
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s.title() if "%b" in fmt else s, fmt).date()
        except ValueError:
            continue
    return None


def parse_datetime(text: str | None) -> datetime | None:
    """`07-Nov-2026 18:40:29` (IST, as NSE prints it) as an aware datetime."""
    if not text:
        return None
    s = text.strip()
    for fmt in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d-%b-%Y %H:%M"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def _num(text: str | None) -> float | None:
    if text is None:
        return None
    s = text.strip().replace(",", "")
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _int(text: str | None) -> int | None:
    v = _num(text)
    return None if v is None else int(round(v))


def _text(value: Any) -> str:
    """Unescape entities (&#8377; is the rupee sign) and collapse whitespace."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", html.unescape(str(value))).strip()


# --- announcements ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Announcement:
    exchange_id: str  # NSE seq_id
    symbol: str
    reported_isin: str | None  # NSE sometimes reports a superseded ISIN here
    company_name: str
    subject: str  # NSE's own category label, e.g. "Credit Rating"
    text: str  # NSE's one-line description of the attachment
    summary: str | None  # NSE's generated summary, present on a minority of filings
    attachment_url: str | None
    filed_at: datetime
    industry: str | None
    has_xbrl: bool

    @property
    def body(self) -> str:
        """What the classifier reads after the subject."""
        return " ".join(x for x in (self.text, self.summary) if x)


def parse_announcement(row: Mapping[str, Any]) -> Announcement | None:
    """One row of /api/corporate-announcements; None when it lacks an id, symbol or time."""
    seq = _text(row.get("seq_id"))
    symbol = _text(row.get("symbol")).upper()
    filed = parse_datetime(row.get("an_dt")) or parse_datetime(row.get("sort_date"))
    if not seq or not symbol or filed is None:
        return None
    industry = _text(row.get("smIndustry"))
    return Announcement(
        exchange_id=seq,
        symbol=symbol,
        reported_isin=_text(row.get("sm_isin")) or None,
        company_name=_text(row.get("sm_name")) or symbol,
        subject=_text(row.get("desc")) or "Announcement",
        text=_text(row.get("attchmntText")),
        summary=_text(row.get("voiceSummary")) or None,
        attachment_url=_text(row.get("attchmntFile")) or None,
        filed_at=filed,
        industry=industry if industry and industry != "-" else None,
        has_xbrl=bool(row.get("hasXbrl")),
    )


def parse_announcements(rows: Iterable[Mapping[str, Any]]) -> list[Announcement]:
    """Valid rows, one per exchange id, oldest first."""
    seen: dict[str, Announcement] = {}
    for row in rows:
        a = parse_announcement(row)
        if a is not None:
            seen.setdefault(a.exchange_id, a)
    return sorted(seen.values(), key=lambda a: (a.filed_at, a.exchange_id))


# --- equity master ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ListedEquity:
    symbol: str
    name: str
    series: str
    isin: str
    listed_on: date | None
    face_value: float | None


def _dict_rows(text: str) -> list[dict[str, str]]:
    """CSV rows keyed by upper-case, stripped headers, with stripped values."""
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    try:
        header = [h.strip().upper() for h in next(reader)]
    except StopIteration:
        return []
    out: list[dict[str, str]] = []
    for raw in reader:
        if not raw or not any(c.strip() for c in raw):
            continue
        out.append({h: (raw[i].strip() if i < len(raw) else "") for i, h in enumerate(header)})
    return out


def parse_equity_master(text: str) -> list[ListedEquity]:
    out: list[ListedEquity] = []
    for r in _dict_rows(text):
        symbol, isin = r.get("SYMBOL", "").upper(), r.get("ISIN NUMBER", "").upper()
        if not symbol or not re.fullmatch(r"IN[A-Z0-9]{10}", isin):
            continue
        out.append(
            ListedEquity(
                symbol=symbol,
                name=r.get("NAME OF COMPANY", symbol),
                series=r.get("SERIES", ""),
                isin=isin,
                listed_on=parse_date(r.get("DATE OF LISTING")),
                face_value=_num(r.get("FACE VALUE")),
            )
        )
    return out


# --- daily bars (security-wise delivery file) -----------------------------------------


@dataclass(frozen=True, slots=True)
class DailyBar:
    symbol: str
    series: str
    trade_date: date
    prev_close: float | None
    open: float | None
    high: float | None
    low: float | None
    close: float
    volume: int
    turnover_cr: float | None
    trades: int | None
    delivery_qty: int | None
    delivery_pct: float | None


def parse_delivery_file(text: str) -> list[DailyBar]:
    """sec_bhavdata_full: one bar per symbol, preferring the normal-market series."""
    best: dict[str, tuple[int, DailyBar]] = {}
    for r in _dict_rows(text):
        series = r.get("SERIES", "").upper()
        if series not in EQUITY_SERIES:
            continue
        day = parse_date(r.get("DATE1"))
        close = _num(r.get("CLOSE_PRICE"))
        volume = _int(r.get("TTL_TRD_QNTY"))
        if day is None or close is None or close <= 0 or volume is None:
            continue
        turnover_lacs = _num(r.get("TURNOVER_LACS"))
        bar = DailyBar(
            symbol=r.get("SYMBOL", "").upper(),
            series=series,
            trade_date=day,
            prev_close=_num(r.get("PREV_CLOSE")),
            open=_num(r.get("OPEN_PRICE")),
            high=_num(r.get("HIGH_PRICE")),
            low=_num(r.get("LOW_PRICE")),
            close=close,
            volume=volume,
            turnover_cr=None if turnover_lacs is None else round(turnover_lacs / 100.0, 4),
            trades=_int(r.get("NO_OF_TRADES")),
            delivery_qty=_int(r.get("DELIV_QTY")),
            delivery_pct=_num(r.get("DELIV_PER")),
        )
        rank = EQUITY_SERIES.index(series)
        if bar.symbol and (bar.symbol not in best or rank < best[bar.symbol][0]):
            best[bar.symbol] = (rank, bar)
    return [b for _, b in sorted(best.values(), key=lambda rb: rb[1].symbol)]


# --- index closes ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IndexClose:
    name: str
    trade_date: date
    close: float
    change_pct: float | None


def parse_index_closes(text: str) -> dict[str, IndexClose]:
    """ind_close_all: keyed by upper-case index name ("NIFTY 50")."""
    out: dict[str, IndexClose] = {}
    for r in _dict_rows(text):
        name = re.sub(r"\s+", " ", r.get("INDEX NAME", "")).strip().upper()
        day = parse_date(r.get("INDEX DATE"))
        close = _num(r.get("CLOSING INDEX VALUE"))
        if name and day and close:
            out.setdefault(name, IndexClose(name, day, close, _num(r.get("CHANGE(%)"))))
    return out


# --- corporate actions -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CorporateAction:
    symbol: str
    isin: str | None
    series: str
    subject: str
    ex_date: date
    record_date: date | None


def parse_corporate_actions(rows: Iterable[Mapping[str, Any]]) -> list[CorporateAction]:
    out: list[CorporateAction] = []
    for r in rows:
        series = _text(r.get("series")).upper()
        ex = parse_date(_text(r.get("exDate")))
        symbol = _text(r.get("symbol")).upper()
        if series not in EQUITY_SERIES or ex is None or not symbol:
            continue
        out.append(
            CorporateAction(
                symbol=symbol,
                isin=_text(r.get("isin")) or None,
                series=series,
                subject=_text(r.get("subject")),
                ex_date=ex,
                record_date=parse_date(_text(r.get("recDate"))),
            )
        )
    return out


# --- board meetings --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BoardMeeting:
    symbol: str
    isin: str | None
    meeting_date: date
    purpose: str
    description: str
    announced_at: datetime | None


def parse_board_meetings(rows: Iterable[Mapping[str, Any]]) -> list[BoardMeeting]:
    """NSE lists a meeting once per intimation; rows for the same symbol and date are
    merged, keeping the longest description (it usually names the agenda)."""
    merged: dict[tuple[str, date], BoardMeeting] = {}
    for r in rows:
        symbol = _text(r.get("bm_symbol")).upper()
        day = parse_date(_text(r.get("bm_date")))
        if not symbol or day is None:
            continue
        m = BoardMeeting(
            symbol=symbol,
            isin=_text(r.get("sm_isin")) or None,
            meeting_date=day,
            purpose=_text(r.get("bm_purpose")) or "Board Meeting",
            description=_text(r.get("bm_desc")),
            announced_at=parse_datetime(_text(r.get("bm_timestamp"))),
        )
        key = (symbol, day)
        prev = merged.get(key)
        if prev is None or len(m.description) > len(prev.description):
            merged[key] = m
    return sorted(merged.values(), key=lambda m: (m.meeting_date, m.symbol))


def is_results_meeting(m: BoardMeeting) -> bool:
    return bool(re.search(r"financial results?|\bresults\b|financials", m.description, re.I))


# --- integrated filing (financials) -------------------------------------------------


@dataclass(frozen=True, slots=True)
class IntegratedFiling:
    """One results filing under SEBI's Integrated Filing, with its XBRL."""

    symbol: str
    quarter_end: date
    basis: str  # Consolidated | Standalone
    audited: str | None
    xbrl_url: str
    filed_at: datetime | None
    revision: bool
    seq_id: str
    taxonomy: str  # indas | nbfc | banking | other, from the XBRL file name


def parse_integrated_filings(payload: Any) -> list[IntegratedFiling]:
    """Financials rows with an XBRL file, newest first; governance rows are dropped."""
    rows = payload.get("data", []) if isinstance(payload, Mapping) else payload
    out: list[IntegratedFiling] = []
    for r in rows or []:
        if "financial" not in _text(r.get("type")).lower():
            continue
        url = _text(r.get("xbrl"))
        qe = parse_date(_text(r.get("qe_Date")))
        basis = _text(r.get("consolidated")).title()
        if not url.endswith(".xml") or qe is None or basis not in {"Consolidated", "Standalone"}:
            continue
        name = url.rsplit("/", 1)[-1].upper()
        taxonomy = (
            "banking"
            if "BANKING" in name
            else "nbfc"
            if "NBFC" in name
            else "indas"
            if "INDAS" in name
            else "other"
        )
        out.append(
            IntegratedFiling(
                symbol=_text(r.get("symbol")).upper(),
                quarter_end=qe,
                basis=basis,
                audited=_text(r.get("audited")) or None,
                xbrl_url=url,
                filed_at=parse_datetime(_text(r.get("broadcast_Date")))
                or parse_datetime(_text(r.get("creation_Date"))),
                revision=_text(r.get("type_Sub")).lower() == "revision",
                seq_id=_text(r.get("seq_Id")),
                taxonomy=taxonomy,
            )
        )
    return sorted(
        out,
        key=lambda f: (f.quarter_end, f.filed_at or datetime.min.replace(tzinfo=IST)),
        reverse=True,
    )


def pick_filing(
    filings: Sequence[IntegratedFiling], quarter_end: date, basis: str
) -> IntegratedFiling | None:
    """The latest filing (a revision beats the original) for one quarter and basis."""
    for f in filings:  # newest first
        if f.quarter_end == quarter_end and f.basis == basis:
            return f
    return None


# --- client ----------------------------------------------------------------------------


class NseError(RuntimeError):
    pass


class NseClient:
    """Fetches with browser-like headers, one request at a time, with retries.

    NSE answers the API from cookies set by its home page; on 401/403 the client visits
    the home page once and retries.
    """

    def __init__(self, min_interval_s: float = 0.6, retries: int = 3, timeout_s: float = 45.0):
        import httpx

        self._api = httpx.Client(
            headers={
                "User-Agent": UA,
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": HOME,
            },
            http2=True,
            follow_redirects=True,
            timeout=timeout_s,
        )
        self._files = httpx.Client(
            headers={"User-Agent": UA}, follow_redirects=True, timeout=timeout_s * 2
        )
        self._min_interval = min_interval_s
        self._retries = retries
        self._last = 0.0
        self._warmed = False

    def close(self) -> None:
        self._api.close()
        self._files.close()

    def _pace(self) -> None:
        wait = self._min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def _get(self, api: bool, url: str, params: Mapping[str, str] | None = None) -> Any:
        import httpx

        client = self._api if api else self._files
        last_error = ""
        for attempt in range(self._retries):
            self._pace()
            try:
                r = client.get(url, params=params)
            except httpx.TransportError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if r.status_code == 404:
                    return None
                if r.status_code in (401, 403) and api and not self._warmed:
                    self._warmed = True
                    self._pace()
                    self._api.get(HOME)
                    continue
                if r.status_code < 400:
                    return r
                last_error = f"HTTP {r.status_code}"
            time.sleep(1.5 * (2**attempt))
        raise NseError(f"{url}: {last_error}")

    def _json(self, path: str, **params: str) -> Any:
        r = self._get(True, f"{API}/{path}", params)
        return [] if r is None else r.json()

    def announcements(self, day_from: date, day_to: date, symbol: str | None = None) -> list[Any]:
        params = {"index": "equities", "from_date": _dmy(day_from), "to_date": _dmy(day_to)}
        if symbol:
            params["symbol"] = symbol
        data = self._json("corporate-announcements", **params)
        return list(data) if isinstance(data, list) else []

    def board_meetings(self, day_from: date, day_to: date) -> list[Any]:
        data = self._json(
            "corporate-board-meetings",
            index="equities",
            from_date=_dmy(day_from),
            to_date=_dmy(day_to),
        )
        return list(data) if isinstance(data, list) else []

    def corporate_actions(self, day_from: date, day_to: date) -> list[Any]:
        data = self._json(
            "corporates-corporateActions",
            index="equities",
            from_date=_dmy(day_from),
            to_date=_dmy(day_to),
        )
        return list(data) if isinstance(data, list) else []

    def equity_master(self) -> str:
        r = self._get(False, f"{ARCHIVES}/content/equities/EQUITY_L.csv")
        if r is None:
            raise NseError("EQUITY_L.csv not found")
        return str(r.text)

    def delivery_file(self, day: date) -> str | None:
        """None on holidays and before the file is published (about 18:00 IST)."""
        r = self._get(False, f"{ARCHIVES}/products/content/sec_bhavdata_full_{day:%d%m%Y}.csv")
        return None if r is None else str(r.text)

    def integrated_filings(self, symbol: str) -> Any:
        return self._json("integrated-filing-results", index="equities", symbol=symbol)

    def fetch_text(self, url: str) -> str | None:
        """A file from NSE's archives (XBRL, CSV); None when it is not there."""
        if not url.startswith(ARCHIVES + "/"):
            raise NseError(f"refusing to fetch outside NSE archives: {url}")
        r = self._get(False, url)
        return None if r is None else str(r.text)

    def index_closes(self, day: date) -> str | None:
        r = self._get(False, f"{ARCHIVES}/content/indices/ind_close_all_{day:%d%m%Y}.csv")
        return None if r is None else str(r.text)


def _dmy(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def trading_days_back(end: date, n: int, holidays: Sequence[date] = ()) -> list[date]:
    """The last `n` weekdays up to and including `end`, oldest first, minus holidays.
    A missing file still marks a holiday the calendar does not know about."""
    out: list[date] = []
    d = end
    skip = set(holidays)
    while len(out) < n:
        if d.weekday() < 5 and d not in skip:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]
