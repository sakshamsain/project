import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from finn.push.results import build_results_card, last_quarter_end_before

NSE = Path(__file__).resolve().parents[3] / "fixtures" / "nse"
FILES = {  # XBRL file name on NSE -> recorded fixture
    f"INTEGRATED_FILING_INDAS_{key}_WEB.xml": f"xbrl_TATASTEEL_{quarter}_consolidated.xml"
    for key, quarter in (
        ("1755442_07112026053333", "Q2FY27"),
        ("1705622_30072026075610", "Q1FY27"),
        ("1572729_12112025073451", "Q2FY26"),
    )
}
FILES["INTEGRATED_FILING_BANKING_1740913_17102026054812_WEB.xml"] = (
    "xbrl_HDFCBANK_Q2FY27_consolidated.xml"
)


class Recorded:
    """NSE as recorded on 8 Nov 2026."""

    def __init__(self, missing: set[str] | None = None) -> None:
        self.missing = missing or set()

    def integrated_filings(self, symbol: str) -> Any:
        return json.loads((NSE / f"integrated_filing_{symbol}.json").read_text())

    def fetch_text(self, url: str) -> str | None:
        name = FILES.get(url.rsplit("/", 1)[-1])
        if name is None or name in self.missing:
            return None
        return (NSE / name).read_text()


def test_quarter_of_a_filing_date() -> None:
    assert last_quarter_end_before(date(2026, 11, 7)) == date(2026, 9, 30)
    assert last_quarter_end_before(date(2026, 10, 1)) == date(2026, 9, 30)
    assert last_quarter_end_before(date(2026, 5, 15)) == date(2026, 3, 31)


def test_tata_steel_card_with_qoq_and_yoy() -> None:
    card = build_results_card(Recorded(), "TATASTEEL", date(2026, 9, 30))
    assert card["status"] == "ok"
    assert card["period"] == "Q2 FY27" and card["basis"] == "Consolidated"
    assert card["compared_with"] == {"previous_quarter": "Q1 FY27", "year_ago": "Q2 FY26"}
    rows = {r["name"]: r for r in card["rows"]}
    assert rows["Revenue"]["value"] == pytest.approx(65436.24)
    assert rows["PAT"]["value"] == pytest.approx(3699.59)
    for r in card["rows"]:
        assert r["qoq_pct"] is not None and r["yoy_pct"] is not None
    assert set(card["_lines"]) == {"Q2 FY27", "Q1 FY27", "Q2 FY26"}


def test_missing_comparison_is_left_out_not_guessed() -> None:
    card = build_results_card(
        Recorded(missing={"xbrl_TATASTEEL_Q2FY26_consolidated.xml"}), "TATASTEEL", date(2026, 9, 30)
    )
    assert card["status"] == "ok"
    assert card["compared_with"]["year_ago"] is None
    assert all(r["yoy_pct"] is None for r in card["rows"])
    assert all(r["qoq_pct"] is not None for r in card["rows"])


def test_quarter_not_filed_yet_waits() -> None:
    card = build_results_card(Recorded(), "TATASTEEL", date(2026, 12, 31))
    assert card["status"] == "waiting"


def test_bank_card_shows_nii_and_ppop_without_a_margin() -> None:
    card = build_results_card(Recorded(), "HDFCBANK", date(2026, 9, 30))
    assert card["status"] == "ok" and card["lender"] is True
    rows = {r["name"]: r for r in card["rows"]}
    assert list(rows) == ["NII", "PPOP", "PBT", "PAT"]
    assert rows["NII"]["value"] == pytest.approx(44464.2)
    assert rows["PPOP"]["value"] == pytest.approx(32871.54)
    assert rows["PBT"]["value"] == pytest.approx(27825.48)
    assert rows["PAT"]["value"] == pytest.approx(20700.03)
    assert card["margin_pct"] is None
