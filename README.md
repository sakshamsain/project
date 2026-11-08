# FINN

A mobile-first financial investment agent that works like an editor with a memory.

- **The Brief (push):** every filing across your portfolio for a window you choose,
  grouped into events and ranked into three tiers. Results arrive as a Revenue, EBITDA,
  PBT and PAT card with QoQ and YoY; management changes arrive as a card on the incoming
  person; end-of-day price and volume alerts fire on thresholds you set.
- **The Dossier (pull):** any NSE ticker becomes a cited research view built only from
  annual reports, results and concall transcripts, centred on a **Promise Ledger** of what
  management guided against what it delivered.

> Status: build week, 8–15 Nov 2026. This README grows with the build; see
> `docs/BUILD_LOG.md` for progress.

## Repository

| Path | What lives there |
| --- | --- |
| `apps/worker` | Python workers on Modal: ingestion, push pipeline, research engine |
| `apps/web` | Next.js PWA on Vercel (read path only) |
| `db/migrations` | Postgres schema, shared by both runtimes |
| `docs` | Decisions, build log, runbook |

## Run the worker tests

```bash
cd apps/worker
uv sync --group dev
uv run pytest -q
```

## Design rules

Code computes every number; rules classify before models do; model output is grounded
in primary filings with page citations; holdings never enter a prompt. See
`docs/DECISIONS.md`.
