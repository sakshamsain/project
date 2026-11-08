# FINN

A mobile-first financial investment agent that works like an editor with a memory.

- **The Brief (push):** every filing across your portfolio for a window you choose,
  grouped into events and ranked into three tiers. Results arrive as a Revenue, EBITDA,
  PBT and PAT card with QoQ and YoY; management changes arrive as a card on the incoming
  person; end-of-day price and volume alerts fire on thresholds you set.
- **The Dossier (pull):** any NSE ticker becomes a cited research view built only from
  annual reports, results and concall transcripts, centred on a **Promise Ledger** of what
  management guided against what it delivered.

**Live:** https://finn-blue.vercel.app (opens on a demo portfolio of 18 NSE companies;
add or remove one and your device gets its own copy).

> Status: build week, 8–15 Nov 2026. This README grows with the build; see
> `docs/BUILD_LOG.md` for progress.

## Repository

| Path | What lives there |
| --- | --- |
| `apps/worker` | Python workers on Modal: ingestion, push pipeline, research engine |
| `apps/web` | Next.js PWA on Vercel (read path only) |
| `db/migrations` | Postgres schema, shared by both runtimes |
| `docs` | Decisions, build log, runbook |

## Run it

```bash
# worker: tests (database tests need a local Postgres with pgvector)
cd apps/worker
uv sync --group dev --extra ingest --extra db
FINN_TEST_DATABASE_URL=postgresql:///postgres uv run pytest -q

# worker: deploy schedules, backfill, replay after a rules change
export FINN_ENV_FILE=~/.secrets/finn.env
uv run python -m finn.ops.envrun modal deploy -m finn.ops.modal_app
uv run python -m finn.ops.envrun modal run -m finn.ops.modal_app::backfill

# web
cd apps/web && npm install && npm run build
```

## How the Brief is made

1. Every 5 minutes the worker reads NSE's announcements for the day and archives the raw rows.
2. Each filing is classified by `rules.yaml` (93% of real filings match a rule); the
   rest are marked for the small model.
3. Filings of one company and family within a window (3 days for results, 2 for board
   changes) become one event; press releases never merge.
4. Each event is scored: category weight, size, price reaction, novelty, with floors for
   top-management or auditor exits, downgrades and pledge increases.
5. `brief()` in Postgres ranks a profile's events for the chosen window: at most five on
   the front page, the rest in brief or folded as routine.
6. After the close, every listed stock is checked for unusual volume, price and delivery;
   each move is tied to the filing that explains it, or flagged as unexplained.

## Design rules

Code computes every number; rules classify before models do; model output is grounded
in primary filings with page citations; holdings never enter a prompt. See
`docs/DECISIONS.md`.


## How the Promise Ledger is made

1. For any NSE symbol, the worker finds the last four earnings-call transcripts filed with
   NSE (AGM and investor-day transcripts are skipped) and stores each page's text.
2. A model lists management's forward-looking promises, copying each sentence word for
   word with its page.
3. Code keeps a promise only if the sentence is in the transcript, keeps a figure only if
   it appears in the sentence, requires the sentence to name the measure, and marks
   segment targets and adjusted figures.
4. Code computes the result for the promised period from the company's quarterly XBRL
   filings and marks it delivered, missed, on track, off track, too early, or not in the
   filings, with the comparison written out.
5. Type a symbol on the Research tab and a ledger is built in about a minute.
