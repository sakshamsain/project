"""Which dossiers the nightly job rebuilds."""

from __future__ import annotations

from finn.core.db import Jsonb, connect, fetch_all
from finn.ops.jobs import stale_dossiers

COMPANIES = {"INE1": "AAA", "INE2": "BBB", "INE3": "CCC", "INE4": "DDD"}


def _seed(url: str) -> None:
    with connect(url) as conn:
        fetch_all(conn, "insert into profiles (id) values ('00000000-0000-4000-8000-0000000000aa')")
        for isin, sym in COMPANIES.items():
            fetch_all(conn, "insert into companies (isin, name) values (%s, %s)", [isin, sym])
            fetch_all(
                conn,
                "insert into company_aliases (isin, kind, value, valid_from)"
                " values (%s, 'nse_symbol', %s, '2000-01-01')",
                [isin, sym],
            )
            fetch_all(
                conn,
                "insert into holdings (profile_id, isin)"
                " values ('00000000-0000-4000-8000-0000000000aa', %s)",
                [isin],
            )
        # AAA and BBB have full dossiers built an hour ago; CCC lacks the annual reports.
        for isin in ("INE1", "INE2", "INE3"):
            for section in ("ledger", "annual_reports") if isin != "INE3" else ("ledger",):
                fetch_all(
                    conn,
                    "insert into dossier_sections (isin, section, docset_hash, prompt_version,"
                    " body, built_at)"
                    " values (%s, %s, 'latest', 'v', %s, now() - interval '1 hour')",
                    [isin, section, Jsonb({})],
                )
        # BBB filed a transcript after its dossier was built; AAA only a routine filing.
        for isin, category, subject in (
            ("INE2", "earnings_call", "Transcript of the earnings call"),
            ("INE1", "routine", "Trading window closure"),
        ):
            fetch_all(
                conn,
                "insert into filings (isin, exchange, exchange_id, filed_at, subject, category)"
                " values (%s, 'NSE', %s, now(), %s, %s)",
                [isin, f"{isin}-1", subject, category],
            )


def test_only_stale_dossiers_are_rebuilt(clean_db: str) -> None:
    _seed(clean_db)
    stale = {r["symbol"] for r in stale_dossiers(clean_db)}
    # DDD has none, CCC lacks annual reports, BBB has a new transcript; AAA is current.
    assert stale == {"BBB", "CCC", "DDD"}
