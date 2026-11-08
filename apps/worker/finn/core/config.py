"""Runtime configuration from environment variables.

Secrets come from the platform's secret store (Modal, Vercel) or, locally, from an env
file outside the repo passed via FINN_ENV_FILE. Nothing secret is ever committed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_env_file(path: str | Path) -> dict[str, str]:
    """Parse KEY=VALUE lines without evaluating anything; comments and blanks skipped."""
    values: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True, slots=True)
class Settings:
    env: str
    database_url: str | None
    gemini_api_key: str | None
    groq_api_key: str | None
    tavily_api_key: str | None
    s3_endpoint: str | None
    s3_access_key_id: str | None
    s3_secret_access_key: str | None
    s3_region: str | None
    s3_bucket: str
    sentry_dsn: str | None
    vapid_public_key: str | None
    vapid_private_key: str | None
    vapid_subject: str

    def require(self, *names: str) -> None:
        missing = [n for n in names if not getattr(self, n)]
        if missing:
            raise RuntimeError(f"missing configuration: {', '.join(missing)}")


def load_settings(environ: dict[str, str] | None = None) -> Settings:
    env = dict(os.environ if environ is None else environ)
    env_file = env.get("FINN_ENV_FILE")
    if env_file and Path(env_file).exists():
        env = {**load_env_file(env_file), **env}
    g = env.get
    return Settings(
        env=g("FINN_ENV", "dev"),
        database_url=g("DATABASE_URL"),
        gemini_api_key=g("GEMINI_API_KEY"),
        groq_api_key=g("GROQ_API_KEY"),
        tavily_api_key=g("TAVILY_API_KEY"),
        s3_endpoint=g("AWS_ENDPOINT_URL_S3"),
        s3_access_key_id=g("AWS_ACCESS_KEY_ID"),
        s3_secret_access_key=g("AWS_SECRET_ACCESS_KEY"),
        s3_region=g("AWS_REGION"),
        s3_bucket=g("S3_BUCKET", "finn-docs"),
        sentry_dsn=g("SENTRY_DSN"),
        vapid_public_key=g("VAPID_PUBLIC_KEY"),
        vapid_private_key=g("VAPID_PRIVATE_KEY"),
        vapid_subject=g("VAPID_SUBJECT", "mailto:alerts@finn.invalid"),
    )
