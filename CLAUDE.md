# FINN: working conventions for coding agents

FINN is a mobile-first investment agent for the ENAM AI Engineer build challenge: a
**Brief** (push: filings ranked into three tiers, results and management-change cards,
end-of-day alerts) and a **Dossier** (pull: cited research on any NSE ticker, centred on
a Promise Ledger of guidance against delivery). The full plan lives in the
"FINN Build Plan" doc; the decisions that matter are summarised in `docs/DECISIONS.md`.

## Layout

- `apps/worker/` – Python 3.12+, deployed on Modal. Ingestion, push pipeline, research engine.
- `apps/web/` – Next.js PWA on Vercel. Reads Postgres; never calls Python on the read path.
- `db/migrations/` – SQL, the contract between both runtimes. Append-only.
- `evals/`, `fixtures/`, `docs/`.

## Commands (worker)

```bash
cd apps/worker
uv sync --group dev --extra ingest
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

## Rules that are not negotiable

1. **Code computes every number.** Models extract, classify and phrase; they never do
   arithmetic that reaches the user. Ratios, QoQ/YoY, margins and scores live in code
   with unit tests.
2. **Rules before models.** Try `finn/push/rules.yaml` first; call a model only when no
   rule matches. Route models by tier through `finn/llm` (tiers in `models.yaml`), never
   by hard-coding a model ID.
3. **Grounding.** Pull-side text cites a page or a computed fact id. Extracted quotes must
   pass `finn.pull.quotes.verify_quote` or they are dropped. Prompts are closed-book.
4. **No portfolio data in prompts.** Only public filings go to models; personalisation
   happens in code.
5. **Secrets stay out of git.** Use `FINN_ENV_FILE` pointing outside the repo locally;
   Modal and Vercel secret stores in production.
6. **Generated text passes `finn.llm.style_lint`.** Lead with the number; no filler, no advice.
7. **Every pure function gets a test**; every source adapter gets a recorded fixture.
8. **Never show a wrong number.** If `consistency_failures` is non-empty, render
   "Numbers need a look" with the filing link.

## Conventions

- Amounts in INR crore; periods as Indian fiscal labels (`Q2 FY27` = Jul–Sep 2026).
- ISIN is the canonical company key; symbols are aliases with validity dates.
- Commits: conventional style (`feat(push): …`), one workstream per PR.
- Log each working day in `docs/BUILD_LOG.md`: what was asked, what went wrong, what changed.
