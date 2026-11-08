"""Reference data: every listed company, and the demo profile reviewers land on."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from finn.core.db import Conn, copy_upsert, fetch_all
from finn.sources.nse import ListedEquity

# The demo profile's id is fixed so the web app can show it before a device has its own.
DEMO_PROFILE_ID = "00000000-0000-4000-8000-00000000f1a0"

# 18 names across 14 sectors; five report September-quarter results in build week.
DEMO_PORTFOLIO: tuple[str, ...] = (
    "HDFCBANK",  # private bank: NII and PPOP instead of EBITDA
    "SBIN",  # public bank: heavy filer, tests clustering
    "MUTHOOTFIN",  # gold-loan NBFC
    "HCLTECH",  # IT services: numeric guidance for the ledger
    "PERSISTENT",  # IT services peer
    "SUNPHARMA",  # pharma disclosures
    "HINDUNILVR",  # FMCG: low-volatility baseline
    "LT",  # engineering: order wins
    "TATAPOWER",  # power: board meeting 11 Nov
    "ASHOKLEY",  # commercial vehicles: board meeting 14 Nov
    "TATASTEEL",  # metals
    "ETERNAL",  # renamed from Zomato
    "DIXON",  # electronics manufacturing
    "POLYCAB",  # cables and wires
    "COCHINSHIP",  # shipbuilding: board meeting 10 Nov
    "DEEPAKNTR",  # chemicals
    "AHLUCONT",  # small cap construction: board meeting 14 Nov
    "AGL",  # small cap logistics: board meeting 14 Nov
)


def seed_companies(conn: Conn, equities: Sequence[ListedEquity]) -> int:
    """Upsert companies and their current NSE symbols from the equity master."""
    by_isin = {e.isin: e for e in equities}
    copy_upsert(
        conn,
        "companies",
        ["isin", "name", "listed_on"],
        [(e.isin, e.name, ["NSE"]) for e in by_isin.values()],
        conflict=["isin"],
        update=["name", "listed_on"],
    )
    copy_upsert(
        conn,
        "company_aliases",
        ["isin", "kind", "value", "valid_from"],
        [(e.isin, "nse_symbol", e.symbol, date(1900, 1, 1)) for e in by_isin.values()],
        conflict=["kind", "value", "valid_from"],
        update=["isin"],
    )
    return len(by_isin)


def seed_demo_profile(conn: Conn, symbols: Sequence[str] = DEMO_PORTFOLIO) -> list[str]:
    """Create the demo profile and its holdings; returns symbols that could not be found."""
    fetch_all(
        conn,
        "insert into profiles (id, is_demo) values (%s, true) on conflict (id) do nothing",
        [DEMO_PROFILE_ID],
    )
    rows = fetch_all(
        conn,
        "select value, isin from company_aliases"
        " where kind = 'nse_symbol' and value = any(%s) and valid_to is null",
        [list(symbols)],
    )
    isin_of = {r["value"]: r["isin"] for r in rows}
    weight = round(1.0 / len(symbols), 4) if symbols else None
    copy_upsert(
        conn,
        "holdings",
        ["profile_id", "isin", "weight"],
        [(DEMO_PROFILE_ID, isin_of[s], weight) for s in symbols if s in isin_of],
        conflict=["profile_id", "isin"],
    )
    return [s for s in symbols if s not in isin_of]
