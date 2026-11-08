"""Postgres access for the worker runtime.

Workers on Modal talk to Neon over TCP with psycopg. Neon's pooled endpoint runs
PgBouncer in transaction mode, so the worker connects to the direct endpoint and turns
prepared statements off either way. The web app reads over Neon's HTTPS driver instead,
and migrations from a laptop go through `finn.core.migrate.NeonHttp`.

Values come back typed (int, Decimal, datetime, dict for jsonb), unlike the HTTPS driver.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterable, Iterator, Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

Row = dict[str, Any]
Conn = psycopg.Connection[Row]

__all__ = ["Conn", "Jsonb", "Row", "connect", "copy_upsert", "direct_url", "fetch_all"]


def direct_url(url: str) -> str:
    """Neon's pooled host carries a `-pooler` suffix; the direct host drops it."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if "-pooler." not in host:
        return url
    return urlunsplit(
        parts._replace(netloc=parts.netloc.replace(host, host.replace("-pooler.", ".", 1)))
    )


@contextlib.contextmanager
def connect(url: str, application_name: str = "finn-worker") -> Iterator[Conn]:
    """A connection that commits when the block exits cleanly and rolls back otherwise."""
    with psycopg.connect(
        direct_url(url),
        row_factory=dict_row,
        prepare_threshold=None,
        connect_timeout=20,
        application_name=application_name,
    ) as conn:
        yield conn


def fetch_all(conn: Conn, query: str, params: Sequence[Any] | None = None) -> list[Row]:
    with conn.cursor() as cur:
        cur.execute(query.encode(), params)
        return cur.fetchall() if cur.description else []


def copy_upsert(
    conn: Conn,
    table: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
    conflict: Sequence[str],
    update: Sequence[str] = (),
    returning: Sequence[str] = (),
) -> list[Row]:
    """Bulk upsert: COPY into a temporary table shaped like `table`, then one
    INSERT ... SELECT ... ON CONFLICT. With no `update` columns, conflicts are skipped,
    so `returning` yields only the rows that were new."""
    stage = sql.Identifier(f"_stage_{uuid.uuid4().hex[:10]}")
    cols = sql.SQL(", ").join(sql.Identifier(c) for c in columns)
    target = sql.Identifier(table)
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("create temp table {} on commit drop as select {} from {} with no data").format(
                stage, cols, target
            )
        )
        with cur.copy(sql.SQL("copy {} ({}) from stdin").format(stage, cols)) as copy:
            for r in rows:
                copy.write_row(r)
        action = (
            sql.SQL("do update set {}").format(
                sql.SQL(", ").join(
                    sql.SQL("{} = excluded.{}").format(sql.Identifier(c), sql.Identifier(c))
                    for c in update
                )
            )
            if update
            else sql.SQL("do nothing")
        )
        keys = sql.SQL(", ").join(sql.Identifier(c) for c in conflict)
        # DISTINCT ON keeps one staged row per key: ON CONFLICT cannot touch a row twice.
        statement = sql.SQL(
            "insert into {} ({}) select distinct on ({}) {} from {} on conflict ({}) {}"
        ).format(target, cols, keys, cols, stage, keys, action)
        if returning:
            statement = sql.SQL("{} returning {}").format(
                statement, sql.SQL(", ").join(sql.Identifier(c) for c in returning)
            )
        cur.execute(statement)
        out = cur.fetchall() if returning else []
        cur.execute(sql.SQL("drop table {}").format(stage))
        return out
