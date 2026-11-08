"""Apply db/migrations/*.sql in order, exactly once, with checksums.

Migrations are append-only: a shipped file whose checksum changes is an error.
Each file runs in one transaction together with its `schema_migrations` row.

Transports:
- `NeonHttp` uses Neon's HTTPS SQL endpoint, for places where raw TCP to Postgres is
  blocked (sandboxes, some CI runners). Standard library only.
- CI applies migrations with `psql` against a pgvector service container.

Usage:
    FINN_ENV_FILE=/path/outside/repo.env python -m finn.core.migrate [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from finn.core.config import load_settings

BOOKKEEPING = """
create table if not exists schema_migrations (
  version     text primary key,
  checksum    text not null,
  applied_at  timestamptz not null default now()
)
"""


def split_statements(sql: str) -> list[str]:
    """Split SQL on top-level semicolons, respecting quotes, comments and dollar quotes."""
    out: list[str] = []
    buf: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if c == "-" and nxt == "-":  # line comment: drop it
            j = sql.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "/" and nxt == "*":  # block comment: drop it
            j = sql.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if c in ("'", '"'):  # quoted literal or identifier; doubled quote escapes
            j = i + 1
            while j < n:
                if sql[j] == c:
                    if j + 1 < n and sql[j + 1] == c:
                        j += 2
                        continue
                    break
                j += 1
            buf.append(sql[i : j + 1])
            i = j + 1
            continue
        if c == "$":  # dollar quote: $$...$$ or $tag$...$tag$
            j = sql.find("$", i + 1)
            tag = sql[i : j + 1] if j != -1 else ""
            if tag and (tag == "$$" or tag[1:-1].replace("_", "").isalnum()):
                end = sql.find(tag, j + 1)
                end = n if end == -1 else end + len(tag)
                buf.append(sql[i:end])
                i = end
                continue
        if c == ";":
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Migration:
    version: str  # file stem, e.g. "0001_init"
    sql: str

    @property
    def checksum(self) -> str:
        return checksum(self.sql)


def discover(directory: Path) -> list[Migration]:
    return [
        Migration(p.stem, p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.sql"))
    ]


def plan(migrations: Sequence[Migration], applied: dict[str, str]) -> list[Migration]:
    """Pending migrations, in order. Raises if a shipped file was edited."""
    for m in migrations:
        if m.version in applied and applied[m.version] != m.checksum:
            raise RuntimeError(f"migration {m.version} changed after it was applied")
    return [m for m in migrations if m.version not in applied]


class Transport(Protocol):
    def query(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]: ...

    def transaction(self, statements: Sequence[tuple[str, Sequence[Any]]]) -> None: ...


class NeonHttp:
    """Neon's HTTPS SQL endpoint (the same one the serverless driver uses)."""

    def __init__(self, database_url: str, timeout_s: float = 60.0) -> None:
        host = urlsplit(database_url).hostname
        if not host:
            raise ValueError("DATABASE_URL has no host")
        self._endpoint = f"https://{host}/sql"
        self._url = database_url
        self._timeout = timeout_s

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            self._endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Neon-Connection-String": self._url, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                payload: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
                return payload
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"Neon HTTP {exc.code}: {detail}") from None

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = self._post({"query": sql, "params": list(params)}).get(
            "rows", []
        )
        return rows

    def transaction(self, statements: Sequence[tuple[str, Sequence[Any]]]) -> None:
        self._post({"queries": [{"query": s, "params": list(p)} for s, p in statements]})


def migrate(
    transport: Transport, migrations: Sequence[Migration], dry_run: bool = False
) -> list[str]:
    transport.query(BOOKKEEPING)
    applied = {
        r["version"]: r["checksum"]
        for r in transport.query("select version, checksum from schema_migrations")
    }
    pending = plan(migrations, applied)
    if dry_run:
        return [m.version for m in pending]
    for m in pending:
        statements: list[tuple[str, Sequence[Any]]] = [(s, ()) for s in split_statements(m.sql)]
        statements.append(
            (
                "insert into schema_migrations (version, checksum) values ($1, $2)",
                (m.version, m.checksum),
            )
        )
        transport.transaction(statements)
    return [m.version for m in pending]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    default_dir = Path(__file__).resolve().parents[4] / "db" / "migrations"
    parser.add_argument("--dir", type=Path, default=default_dir)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    settings = load_settings()
    settings.require("database_url")
    assert settings.database_url is not None
    done = migrate(NeonHttp(settings.database_url), discover(args.dir), dry_run=args.dry_run)
    verb = "would apply" if args.dry_run else "applied"
    print(f"{verb}: {', '.join(done) if done else 'nothing, schema is current'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
