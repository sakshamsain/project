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
