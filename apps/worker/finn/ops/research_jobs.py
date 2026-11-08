"""Research requests from the app: a job row per request, run on Modal.

The app inserts a `jobs` row (kind "dossier") and pings the worker's endpoint, which
starts it at once. Anything the ping missed is claimed by the next poll, so a request is
never lost. Progress is written to the row as the build goes, and the page shows it.
"""

from __future__ import annotations

from typing import Any

from finn.core.db import Jsonb, connect, fetch_all

KIND = "dossier"


def claim(url: str, job_id: int | None = None) -> dict[str, Any] | None:
    """Mark one queued dossier job running and return it; None if there is none."""
    with connect(url) as conn:
        rows = fetch_all(
            conn,
            "update jobs set status = 'running', started_at = now(), attempts = attempts + 1"
            " where id = (select id from jobs where kind = %s and status = 'queued'"
            "   and (%s::bigint is null or id = %s::bigint)"
            "   order by created_at for update skip locked limit 1)"
            " returning id, payload",
            [KIND, job_id, job_id],
        )
    return rows[0] if rows else None


def set_progress(url: str, job_id: int, message: str) -> None:
    with connect(url) as conn:
        fetch_all(
            conn,
            "update jobs set progress = %s where id = %s",
            [Jsonb({"message": message}), job_id],
        )


def finish(url: str, job_id: int, ok: bool, result: dict[str, Any] | str) -> None:
    with connect(url) as conn:
        fetch_all(
            conn,
            "update jobs set status = %s, finished_at = now(), progress = %s, error = %s"
            " where id = %s",
            [
                "done" if ok else "failed",
                Jsonb(result if isinstance(result, dict) else {"message": "Failed"}),
                None if ok else str(result)[:500],
                job_id,
            ],
        )


def run_job(url: str, nse: Any, llm: Any, job: dict[str, Any]) -> dict[str, Any]:
    from finn.pull.dossier import build_dossier

    job_id = int(job["id"])
    symbol = str((job.get("payload") or {}).get("symbol", "")).upper()
    try:
        out = build_dossier(url, nse, llm, symbol, progress=lambda m: set_progress(url, job_id, m))
    except Exception as exc:
        finish(url, job_id, False, f"{type(exc).__name__}: {exc}")
        return {"job": job_id, "status": "failed"}
    ok = out.get("status") != "unknown symbol"
    finish(url, job_id, ok, {"message": "Done", **out} if ok else str(out.get("status")))
    return {"job": job_id, "status": "done" if ok else "failed"}
