"""FINN's worker on Modal: the schedules and the one-off jobs.

    modal deploy -m finn.ops.modal_app               # schedules go live
    modal run -m finn.ops.modal_app::seed            # companies, symbols, demo profile
    modal run -m finn.ops.modal_app::backfill        # 60 days of filings, 90 of bars
    modal run -m finn.ops.modal_app::eod --day 2026-11-06 --force

Secrets come from the Modal secret `finn-env` (DATABASE_URL, SENTRY_DSN_WORKER, ...).
NSE answers from Modal's network, which is why ingestion runs here and not elsewhere.
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

import modal

app = modal.App("finn")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "httpx[http2]>=0.27",
        "psycopg[binary]>=3.2",
        "pydantic>=2.7",
        "pyyaml>=6.0",
        "sentry-sdk>=2.0",
    )
    # rules.yaml and models.yaml ship with the code; the default filter keeps only .py files.
    .add_local_python_source("finn", ignore=["**/__pycache__", "**/*.pyc"])
)
secrets = [modal.Secret.from_name("finn-env")]
IST = "Asia/Kolkata"


def _setup() -> str:
    dsn = os.environ.get("SENTRY_DSN_WORKER")
    if dsn:
        import sentry_sdk

        sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0, environment="production")
    return os.environ["DATABASE_URL"]


def _client() -> Any:
    from finn.sources.nse import NseClient

    return NseClient()


def _log(name: str, out: dict[str, Any]) -> dict[str, Any]:
    print(json.dumps({"job": name, **out}, default=str))
    return out


@app.function(
    image=image,
    secrets=secrets,
    schedule=modal.Cron("*/5 8-22 * * *", timezone=IST),
    timeout=600,
    max_containers=1,
)
def poll() -> dict[str, Any]:
    """Filings every five minutes from 08:00 to 22:55 IST."""
    from finn.ops.jobs import run_poll

    return _log("poll", run_poll(_setup(), _client()))


@app.function(
    image=image,
    secrets=secrets,
    schedule=modal.Cron("*/30 0-7,23 * * *", timezone=IST),
    timeout=600,
    max_containers=1,
)
def poll_night() -> dict[str, Any]:
    """Every half hour overnight; after midnight it also sweeps yesterday's late filings."""
    from finn.ops.jobs import run_poll

    return _log("poll_night", run_poll(_setup(), _client()))


@app.function(
    image=image,
    secrets=secrets,
    schedule=modal.Cron("10 19-23 * * 1-5", timezone=IST),
    timeout=1800,
    max_containers=1,
)
def eod(day: str = "", force: bool = False) -> dict[str, Any]:
    """Weekday evenings from 19:10 IST, hourly until the delivery file appears."""
    from finn.ops.jobs import run_eod

    d = date.fromisoformat(day) if day else None
    return _log("eod", run_eod(_setup(), _client(), d, force=force))


@app.function(
    image=image,
    secrets=secrets,
    schedule=modal.Cron("40 6 * * 1", timezone=IST),
    timeout=1800,
)
def seed() -> dict[str, Any]:
    """Weekly refresh of listed companies (new listings, renames)."""
    from finn.ops.jobs import run_seed

    return _log("seed", run_seed(_setup(), _client()))


@app.function(image=image, secrets=secrets, timeout=3 * 3600)
def backfill(filing_days: int = 60, price_days: int = 90) -> dict[str, Any]:
    from finn.ops.jobs import run_backfill

    return _log(
        "backfill",
        run_backfill(_setup(), _client(), filing_days=filing_days, price_days=price_days),
    )


@app.function(image=image, secrets=secrets, timeout=3600)
def rescan(sessions: int = 40) -> dict[str, Any]:
    """Recompute anomalies and reactions after a rules change."""
    from finn.ops.jobs import run_rescan

    return _log("rescan", run_rescan(_setup(), sessions))


@app.function(image=image, secrets=secrets, timeout=3 * 3600)
def rebuild(rescan_sessions: int = 45) -> dict[str, Any]:
    """Replay stored filings through the current rules and clustering."""
    from finn.ops.jobs import run_rebuild

    return _log("rebuild", run_rebuild(_setup(), rescan_sessions, nse=_client()))


@app.function(image=image, secrets=secrets, timeout=3600)
def results(days: int = 30, limit: int = 40, force: bool = False) -> dict[str, Any]:
    """Results cards for recent results events on held companies."""
    from finn.ops.jobs import run_results

    return _log("results", run_results(_setup(), _client(), days=days, limit=limit, force=force))


@app.function(image=image, secrets=secrets, timeout=120)
def env_check() -> dict[str, Any]:
    """Which expected settings are present (names only, never values)."""
    names = [
        "DATABASE_URL",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "TAVILY_API_KEY",
        "SENTRY_DSN_WORKER",
        "AWS_ENDPOINT_URL_S3",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "S3_BUCKET",
        "VAPID_PUBLIC_KEY",
        "VAPID_PRIVATE_KEY",
        "VAPID_SUBJECT",
    ]
    return _log("env_check", {n: bool(os.environ.get(n)) for n in names})
