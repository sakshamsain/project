# FINN runbook

How FINN runs in production, what to check when something looks wrong, and how to put
it right. Times are IST.

## What runs where

| Piece | Where | Notes |
|---|---|---|
| Web app (read path) | Vercel, project `finn`, region `iad1` | Reads Postgres over HTTPS as the least-privilege role `finn_web`; never calls Python |
| Worker | Modal app `finn` | Every schedule and job below; secrets in the Modal secret `finn-env` |
| Database | Neon Postgres | Schema in `db/migrations`, applied in order and append-only |
| Models | Gemini (primary), Groq (fallback) | Chosen by tier in `apps/worker/finn/llm/models.yaml`; free tiers, shadow cost logged |

## Schedules (Modal)

| Function | When | What it does |
|---|---|---|
| `poll` | every 5 min, 08:00–22:59 | NSE announcements → filings → events → scores; results cards, people cards, queued research jobs, push |
| `poll_night` | every 30 min, 23:00–07:59 | The same, at a slower pace overnight |
| `eod` | 19:10 Mon–Fri, retried hourly to 23:10 until NSE's files are out | Bhavcopy and delivery for every listed stock, index closes, corporate actions; unusual-move alerts tied to the session's filings |
| `dossiers_nightly` | 02:40 daily | Rebuilds only the dossiers a results filing, call transcript or annual report has made stale |
| `seed` | 06:40 Monday | Refreshes the equity master and symbol aliases |
| `request_research` | on demand (HTTPS) | Queues a reader's research job and spawns `research_job` |

Manual: `backfill`, `rescan`, `rebuild` (re-cluster after a `rules.yaml` change),
`results` (`force=true` to rebuild cards), `people`, `dossier(symbol)`, `history`,
`env_check`.

```bash
cd apps/worker
export FINN_ENV_FILE=~/.secrets/finn.env      # outside the repo; never source it in a shell
uv run python -m finn.ops.envrun modal deploy -m finn.ops.modal_app
uv run python -m finn.ops.envrun modal run -m finn.ops.modal_app::dossier --symbol INFY
uv run python -m finn.ops.envrun python -m finn.core.migrate   # apply pending migrations
```

## Health checks

- **`/status` on the web app** shows, for each NSE source and the end-of-day run, its
  last success and any run of failures (from `source_health`).
- Filings stop arriving: NSE rejects requests without its cookies, so the client warms
  a session first; a run of 401/403 in `source_health.last_error` means NSE changed
  something. NSE is reachable only from Modal, not from every network.
- A results card says "Numbers need a look": a consistency check failed (for example
  revenue less costs not matching profit). This is by design; open the filing link. To
  retry after a parser fix: `modal run ...::results --force true`.
- A dossier shows a year as "numbers need a look": its cash flows or profit did not
  reconcile, or the full year differs from the four quarterly filings. The year is
  withheld on purpose. `cash.reports[*].dropped` in `dossier_sections` says which lines
  failed verification.
- Model errors: `llm_calls` logs every call with its error. A 429 falls back to the next
  model in the tier; repeated failures show in `docs/EVALS.md` (rerun
  `evals/run_evals.py`).
- Push not arriving: check `notifications.status` (`held` during quiet hours 22:00–07:00,
  released at 07:00), and that the browser still has a subscription in `push_subscriptions`.

## Changing things safely

- **Rules:** edit `finn/push/rules.yaml`, run the tests (each rule has fixture cases),
  deploy, then `modal run ...::rebuild` to re-classify and re-cluster recent days.
- **Prompts:** bump the module's `PROMPT_VERSION`. Cached answers are keyed by prompt
  version and input, so old answers are not reused, and stored dossier sections of the
  old version are replaced on the next build.
- **Schema:** add a new numbered file in `db/migrations`; never edit an applied one.
  Grant `select` to `finn_web` for anything the web reads.

## Secrets

Kept only in `~/.secrets/finn.env` locally (loaded by `finn.ops.envrun`), the Modal
secret `finn-env` and Vercel's environment settings. None are in git. After the
assessment (15 Nov 2026): revoke the Vercel, Modal and Sentry tokens used during the
build and rotate the Neon password.
