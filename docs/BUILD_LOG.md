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

## Sun 8 Nov 2026 (Day 0, evening): real data in, Brief live

- **Asked:** build as much as possible today.
- **Went wrong:** sourcing the env file in bash broke on the `&` in the Neon URL and the
  shell's job notice echoed the URL into my session log (not into git or any service);
  added `finn.ops.envrun`, which reads the file as data. Modal's local-source mount skips
  non-Python files by default, which would have dropped `rules.yaml`; overrode the filter.
  The first Vercel project was created without a framework, so every route 404'd; pinned
  `framework: nextjs` in `vercel.json`. Market-wide NSE rows carry no summaries (only
  per-symbol queries do), so headlines lean on NSE's one-line descriptions.
- **Changed:** NSE parsers for six feeds with recorded fixtures; the push pipeline (raw
  archive, rules, clustering into events, scores, tiers) and the EOD job (bars for every
  listed equity, anomalies, links to the explaining filing, reaction rescoring), all
  idempotent. Deployed to Modal with schedules: filings every 5 min from 08:00 to 23:00
  IST, overnight every 30 min, EOD from 19:10 IST on weekdays, weekly company refresh.
  Backfilled 61 sessions of bars (164k rows) and 60 days of filings (32.6k filings) for
  all 2,632 listed equities. Web app live on Vercel: Today (three tiers, window picker,
  results dates), Pulse, company and event pages, portfolio editor, alert limits,
  notification opt-in. 144 worker tests, including database tests on Postgres.

## Sun 8 Nov 2026 (Day 0, late afternoon): results cards and push; paused for the usage limit

- **Changed:** found NSE's Integrated Filing endpoint (`/api/integrated-filing-results`) and
  read each company's own results XBRL: the card compares the reported quarter with the
  previous one and the year-ago one, each from its own filing, all maths in
  `results_math`. Banks and NBFCs show NII and PPOP. 11 of 11 recent results on the demo
  portfolio have cards; results headlines now lead with computed numbers when the
  company's release title has none. Replayed all 32.6k filings through the new rules.
  Web push: subscriptions on the web, sending from the worker (one per front-page event,
  one EOD summary, quiet hours 22:00 to 07:00 IST). 166 worker tests.
- **Went wrong:** the first job run after a Modal deploy was served by a container still
  on the old code; re-ran it. A release whose NSE summary mentioned "investor
  presentation" was filed as a presentation; the summary now decides only when nothing
  else matched.
- **Next:** (1) "Send a test notification" button on Settings; (2) management-change card
  from the appointment filing's own profile text, with verified quotes; (3) the Dossier:
  transcripts and annual reports into `documents`/`doc_pages`, guidance extraction, the
  Promise Ledger against the quarterly figures now stored in `financials`; (4) evals and
  the covering note.
