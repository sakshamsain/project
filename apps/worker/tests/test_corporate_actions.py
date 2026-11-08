import re
from pathlib import Path

import pytest

from finn.core.db import direct_url
from finn.push.corporate_actions import mutes_price_rules, parse_action
from finn.push.score import FRONT_CAP, FRONT_THRESHOLD, ONELINER_THRESHOLD

MIGRATIONS = Path(__file__).resolve().parents[3] / "db" / "migrations"


@pytest.mark.parametrize(
    ("subject", "kind", "amount"),
    [
        ("Interim Dividend - Rs 9.50 Per Share", "dividend", 9.5),
        ("Interim Dividend - Re  1 Per Share", "dividend", 1.0),
        (
            "Final Dividend - Rs 5 Per Share And Special Dividend - Rs 10 Per Share",
            "dividend",
            15.0,
        ),
        ("Bonus 1:1", "bonus", None),
        (
            "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share",
            "split",
            None,
        ),
        ("Buy Back", "buyback", None),
        ("Rights 1:5 @ Premium Rs 90/-", "rights", None),
        ("Annual General Meeting", "other", None),
    ],
)
def test_parse_action(subject: str, kind: str, amount: float | None) -> None:
    a = parse_action(subject)
    assert (a.kind, a.amount_rs) == (kind, amount)


def test_mutes_price_rules() -> None:
    assert mutes_price_rules("Bonus 1:1", 500.0)
    assert mutes_price_rules("Interim Dividend - Rs 25 Per Share", 300.0)  # 8.3% of price
    assert not mutes_price_rules("Interim Dividend - Rs 5.75 Per Share", 2500.0)  # 0.2%
    assert not mutes_price_rules("Interim Dividend - Rs 5 Per Share", None)
    assert not mutes_price_rules("Buy Back", 100.0)


def test_direct_url_drops_the_pooler_suffix() -> None:
    pooled = "postgresql://u:p@ep-x-123-pooler.c-15.us-east-1.aws.neon.tech/db?sslmode=require"
    assert (
        direct_url(pooled)
        == "postgresql://u:p@ep-x-123.c-15.us-east-1.aws.neon.tech/db?sslmode=require"
    )
    assert direct_url("postgresql:///finn_test") == "postgresql:///finn_test"


def test_brief_sql_uses_the_python_tier_constants() -> None:
    sql = (MIGRATIONS / "0002_ingest.sql").read_text()
    body = sql[sql.index("create function brief") :]
    assert set(re.findall(r"score >= ([0-9.]+)", body)) == {
        str(FRONT_THRESHOLD),
        str(ONELINER_THRESHOLD),
    }
    assert f"front_rank <= {FRONT_CAP}" in body
