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
add or remove one and your device gets its own copy, or create an account to keep it on
every device).

What is in the app: the Brief (Today), Pulse (end-of-day moves), company pages with
interactive price and quarterly results charts, a Dossier for any NSE company (Research:
Snapshot, Trajectory, Promises, Cash, Bull vs bear, Sources), results and people cards,
notifications, accounts, and search. Every quote and figure in a Dossier links to the
page of the filing it came from, with the words marked.

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
uv sync --group dev --extra ingest --extra db --extra push --extra docs
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

## How the annual-report half of the Dossier is made

1. The worker takes the last two annual reports from NSE's annual-report feed (a revision
   replaces the original) and reads every page of each, 300 to 600 of them.
2. It finds the parts it needs by what is on the page, not by page number: the
   consolidated statement of profit and loss and statement of cash flows (title near the
   top or bottom of the page, dozens of figures), the independent auditor's report (its
   heading, or its opening paragraph when the heading is an image), BRSR Section A
   (SEBI's fixed format for what a company does) and the MD&A (bookmarks or running
   headers). Only those pages are stored, under their page numbers in the PDF.
3. Statements: a model copies the lines asked for, figures exactly as printed. Code keeps
   a line only if its label is on the page and its two figures are the first two in that
   row (current year first); it reads the unit from the page, converts to ₹ crore, and
   does every sum. Operating, investing and financing flows must add up to the change in
   cash, profit before tax less tax must equal profit, and full-year revenue and profit
   are compared with the four quarterly XBRL filings. A year that fails shows "numbers
   need a look" instead of figures. For capex, dividends and buybacks, code finds the
   lines itself too: a sum is withheld if the model missed one, and a line is dropped if
   code does not recognise it as part of the sum.
4. Business, auditor and risks: quotes the model copied, kept only if they are on the
   page; the auditor's opinion is read from the report's headings; an emphasis-of-matter
   paragraph is cut from the text by code.
5. Bull vs bear: a stronger model writes up to three points each way from a numbered
   list of facts code has already checked or computed; a point is dropped if it cites no
   fact or states a figure its facts do not contain. Both sides are always shown.
