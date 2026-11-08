from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from finn.core.migrate import Migration, discover, migrate, plan, split_statements

MIGRATIONS = Path(__file__).resolve().parents[3] / "db" / "migrations"


def test_split_respects_quotes_comments_and_dollar_quotes() -> None:
    sql = """
    -- a comment; with a semicolon
    create table t (note text default 'a;b', "odd;name" int);
    /* block; comment */
    insert into t (note) values ('it''s; fine');
    create function f() returns int as $body$ begin return 1; end $body$ language plpgsql;
    select 1
    """
    stmts = split_statements(sql)
    assert len(stmts) == 4
    assert "'a;b'" in stmts[0] and '"odd;name"' in stmts[0]
    assert stmts[1].endswith("('it''s; fine')")
    assert "return 1; end" in stmts[2]
    assert stmts[3] == "select 1"


def test_shipped_schema_splits_cleanly() -> None:
    [first] = [m for m in discover(MIGRATIONS) if m.version == "0001_init"]
    stmts = split_statements(first.sql)
    assert stmts[0].startswith("create extension if not exists vector")
    assert sum(s.startswith("create table") for s in stmts) == 23
    assert not any(";" in s for s in stmts)


def test_plan_skips_applied_and_rejects_edited_files() -> None:
    a, b = Migration("0001_a", "select 1;"), Migration("0002_b", "select 2;")
    assert [m.version for m in plan([a, b], {"0001_a": a.checksum})] == ["0002_b"]
    with pytest.raises(RuntimeError, match="changed after it was applied"):
        plan([a, b], {"0001_a": "not-the-same"})


class FakeTransport:
    def __init__(self) -> None:
        self.applied: dict[str, str] = {}
        self.batches: list[list[str]] = []

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        if sql.strip().startswith("select version"):
            return [{"version": v, "checksum": c} for v, c in self.applied.items()]
        return []

    def transaction(self, statements: Sequence[tuple[str, Sequence[Any]]]) -> None:
        self.batches.append([s for s, _ in statements])
        version, check = statements[-1][1]
        self.applied[version] = check


def test_migrate_runs_each_file_once_in_its_own_transaction() -> None:
    t = FakeTransport()
    ms = [Migration("0001_a", "create table a (x int); create table b (y int);")]
    assert migrate(t, ms) == ["0001_a"]
    assert len(t.batches) == 1 and len(t.batches[0]) == 3  # two statements + bookkeeping row
    assert migrate(t, ms) == []  # second run is a no-op
