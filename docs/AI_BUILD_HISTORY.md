# How FINN was built with AI

FINN was built in one week (8–15 Nov 2026) by one person directing Claude (Anthropic's
Claude Opus 5.5, with Claude Fable 5.2 for one stretch) in Claude's cloud workspace,
which gives the model a shell, a Python and Node toolchain, the repository, and access
to Modal, Neon, Vercel and the web. The product itself uses different models (Gemini
and Groq, see `apps/worker/finn/llm/models.yaml`) for the narrow jobs where it needs one.

This file says how the work was directed and checked. `docs/BUILD_LOG.md` is the
day-by-day record (what was asked, what went wrong, what changed), `docs/DECISIONS.md`
holds the 24 decisions with their reasons, and every commit is in the git history.

## What the person asked for

The build was steered by short instructions; the model planned and did the work, and
asked only where a choice was the person's to make (accounts and keys, which repo).

| When (IST) | Instruction | What came of it |
|---|---|---|
| Sun 8 Nov | "Plan this" (with the challenge brief and reference PDFs) | The FINN Build Plan: product, architecture, data sources checked live, evals, risks |
| Sun 8 Nov | API keys, the Neon database, the GitHub repo; "now connect" | Keys stored outside git, schema applied, Modal and Vercel connected |
| Sun 8 Nov | "Build today as much as can" | The Brief, Pulse, results and people cards, push, the Promise Ledger, research on request |
| Sun 8 Nov | "The graphs should be interactive, with authentication and a user-friendly interface" | Interactive charts, accounts, search, a first-run explainer |
| Mon 9 Nov | "Build the next feature" | Annual reports in the Dossier: Cash, Snapshot, auditor, risks, bull and bear, page citations |
| Mon 9 Nov | "Build the remaining app" | Results checked against the ledger, the inbox, nightly dossiers, the balance sheet |
| Tue 10 Nov | "Build the remaining app; the user interface should look good" | The redesign, Brief windows by date and since last visit, evals, these docs |

## How the model was kept honest

The rules in `CLAUDE.md` bind the model as much as the product: code computes every
number, rules come before models, every quote is verified against its page, and a
number that fails a check is never shown. In practice that meant:

1. **Spike before building.** Every data source was called live from Modal on day 0
   (NSE blocks most networks) and the responses were recorded as test fixtures, so the
   code was written against what NSE actually returns, not what its docs suggest.
2. **Tests on real documents.** Parsers and extractors are tested against recorded NSE
   payloads, XBRL files and annual-report pages from 10 companies; model answers used in
   tests are recorded too, so tests never call a model. 251 worker tests run in CI.
3. **Look at the output, not the code.** After each feature the model ran it in
   production and read what came out: the stored figures against the PDFs, and
   screenshots of every screen on a phone and a desktop, in light and dark.
4. **Try it on companies it had not seen.** Asking the live app for a new company
   (Asian Paints on day 1, ten random companies for the evals) found layouts the first
   companies did not have, each fixed and kept as a fixture.

## What the AI got wrong, and how it was caught

Examples from the build log, each caught by a check rather than by luck:

- The model reading a cash-flow statement took a dividend from the next page, a
  statement of changes in equity. Caught because the year's cash flows did not add up;
  fixed by requiring figures to be the first two in their row and stopping a statement
  where the next begins.
- It added TCS's advances for leased assets to capital expenditure (₹109 crore). Caught
  by reading the stored figures against the PDF; now code must also recognise every line
  it sums.
- It read "Tax expense:" (a heading) as the tax line. Caught by the profit identity
  (profit before tax less tax must equal profit).
- Early promise extraction labelled EBIT as EBITDA and segment guidance as company-wide.
  Caught on review of the Infosys ledger; the metric must now be named in the quote, and
  scope is resolved by code.
- The model client's cache handed a retry to a stronger model the weaker model's answer.
  Caught by a test; escalation now skips other models' cached answers.
- The redesign's tab-bar styles also hit the rail's wordmark, so on a phone the tab bar
  showed only the wordmark. Caught from a phone screenshot.

## What stayed with the person

Choosing the product and its name, the accounts and API keys (stored only outside the
repo and in the hosts' secret stores), the decision to keep LinkedIn as a search link
rather than scrape it, and the submission itself.
