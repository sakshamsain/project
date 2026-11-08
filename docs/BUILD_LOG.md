# Build log

Three lines a day: what was asked, what went wrong, what changed.

## Sun 8 Nov 2026 (Day 0)

- **Asked:** a production-grade build plan from the ENAM brief, then to start building
  hands-free. Plan written as a doc (architecture, data, push, pull, AI routing, evals,
  schedule). Accounts created; keys handed over and stored outside the repo.
- **Went wrong:** the sandbox could reach only GitHub at first; later package managers
  opened but model, deploy and market-data hosts stayed blocked. The GitHub link cannot
  create repositories, only use attached ones. A regex bug read "FY2027" as FY20
  (two-digit alternative matched first); caught while writing tests.
- **Changed:** built everything that needs no outside service first: Postgres schema,
  rules-first classifier, materiality score and tiers, end-of-day anomaly rules (with
  corporate-action suppression), results-card maths with accounting checks, Indian
  fiscal periods, Promise Ledger quote verification, house-style lint. 76 tests pass;
  ruff and strict mypy clean. Swapped Cloudflare R2 for Neon's S3 storage.

## Sun 8 Nov 2026 (Day 0, afternoon): connections

- **Asked:** connect everything: GitHub, Neon, Modal, the model APIs, Sentry.
- **Went wrong:** the new repo was outside the Claude GitHub app until access was
  granted. Raw TCP to Postgres is blocked from the build sandbox, so the schema could not
  be applied with psql. The Modal CLI could not get through the sandbox proxy until it
  was installed with its proxy extra and pointed at the proxy's CA. The newest Gemini
  Flash models (3.7, 3.8) answered 503 "high demand" twice. BSE's API returned 403 from
  Modal. I briefly put the owner's email in the web-push contact field; replaced with a
  placeholder before any push was sent.
- **Changed:** wrote `finn.core.migrate` (checksummed, one transaction per file) over
  Neon's HTTPS SQL endpoint; schema is live on Neon (24 tables, pgvector 0.8.6). Created
  the `finn-docs` bucket on Neon storage, the `finn-env` secret on Modal, and Sentry
  projects `finn-worker` and `finn-web`; generated VAPID keys; validated every key.
  Day-0 spike ran on Modal (egress 20.86.121.224): NSE RSS (66 items), NSE announcements
  API (2,485 Tata Power filings), the 6 Nov bhavcopy and delivery files, Screener and
  Yahoo all answered; BSE did not. Pinned model tiers from live calls.
