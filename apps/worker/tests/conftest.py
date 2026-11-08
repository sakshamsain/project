"""Shared fixtures. Database tests need a Postgres with pgvector:

    FINN_TEST_DATABASE_URL=postgresql:///postgres uv run pytest -q

Each session creates a fresh `finn_it` database next to the one given and applies every
migration, so tests see the same schema production does. Without the variable, database
tests are skipped.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = ROOT / "db" / "migrations"
FIXTURES = ROOT / "fixtures"


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    base = os.environ.get("FINN_TEST_DATABASE_URL")
    if not base:
        pytest.skip("FINN_TEST_DATABASE_URL is not set")
    import psycopg
    from psycopg.conninfo import make_conninfo

    from finn.core.migrate import discover, split_statements

    name = "finn_it"
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute(f"drop database if exists {name} with (force)".encode())
        admin.execute(f"create database {name}".encode())
    url = make_conninfo(base, dbname=name)
    with psycopg.connect(url, autocommit=True) as conn:
        for m in discover(MIGRATIONS):
            for statement in split_statements(m.sql):
                conn.execute(statement.encode())
    yield url


@pytest.fixture()
def clean_db(pg_url: str) -> str:
    """The test database with every data table emptied."""
    import psycopg

    with psycopg.connect(pg_url, autocommit=True) as conn:
        tables = [
            r[0]
            for r in conn.execute(
                b"select tablename from pg_tables where schemaname = 'public'"
            ).fetchall()
        ]
        conn.execute(
            (
                "truncate " + ", ".join(f'"{t}"' for t in tables) + " restart identity cascade"
            ).encode()
        )
    return pg_url
