# FINN evals

Measured from production on 10 Nov 2026 15:58 UTC by `evals/run_evals.py`.
Every number is computed by the script from what FINN stored; rerun it to refresh.

## Push: filings ranked without a model

| Measure | Value |
|---|---|
| Filings ingested from NSE | 33,157 |
| Classified by a rule in `rules.yaml` | 25,684 (77.5%) |
| Left uncategorised | 0 |
| Model calls to classify or rank a filing | 0 |
| Events in the last 30 days (filings clustered) | 12,958 from 17,025 filings |
| Read first | 2,676 events (20.7%) |
| One line | 2,545 events (19.6%) |
| Folded as routine | 7,737 events (59.7%) |

Rows from filings before the `classified_by` column was added count as unclassified by rule here even when a rule placed them; the share above is a floor.

## Results cards: figures from XBRL, arithmetic in code

12 results cards built from NSE XBRL filings; 12 passed every consistency check (100.0%). A card that fails shows "Numbers need a look" with the filing link instead of figures.

## Dossier: statements read from annual reports

| Measure | Value |
|---|---|
| Companies with a Cash tab | 31 |
| Fiscal years read (cash flow and profit and loss) | 89 |
| Years passing every identity (shown) | 87 (97.8%) |
| Full-year revenue and profit equal to the four quarterly XBRL filings | 20 of 21 years compared (95.2%) |
| Balance sheets that balance (shown) | 76 of 76 (100.0%) |
| Years with a sum withheld because a line could not be read | 10 |
| Why years were held back | differs_from_quarterly_filings ×1, cash_flows_do_not_add_up ×1 |

The quarterly comparison is the independent check: the annual report and the XBRL results are separate filings, and FINN reads them by separate routes. Lenders are left out of it because their annual revenue line includes items the quarterly XBRL reports elsewhere.

## Dossier: the Promise Ledger

| Measure | Value |
|---|---|
| Ledgers built | 42 |
| Earnings-call transcripts read | 146 |
| Promises kept (quote found verbatim on its page) | 329 |
| Dropped: quote not in the transcript | 32 (8.5% of candidates) |
| Dropped: a figure not stated in the quote | 14 |
| Promises checked by code against filed figures | 11 of 213 (5.2%) |
| Status | delivered 2, missed 2, not measurable 200, off track 2, on track 5, too early 2 |

Every promise shown carries a quote that `verify_quote` found in the transcript text, so no promise is shown in words the company did not use. Most promises are about things the quarterly filings do not report (order inflow, deal wins, store counts) and stay 'not in the filings' rather than being guessed.

## Dossier: bull and bear

31 cases; 177 points kept, 5 dropped by code (2.7% of what the model wrote). A point is dropped if it cites no checked fact, states a figure its facts do not contain, or fails the house style.

## Generalisation: ten companies FINN had not seen

Drawn at random (seed 20261110) from NSE companies that filed results in the last 120 days, then built end to end with no changes to code or prompts.

| Symbol | Calls read | Promises | Annual reports read | Years shown | Quarters match | Bull / bear |
|---|---|---|---|---|---|---|
| GLASSWALL | 1 | 1 | 0 | 0 of 0 | 0 | 0 / 0 |
| MARINE | 0 | 0 | 2 | 2 of 3 | 1 | 3 / 3 |
| PFIZER | 0 | 0 | 2 | 2 of 2 | 1 | 2 / 3 |
| PCJEWELLER | 0 | 0 | 2 | 3 of 3 | 1 | 3 / 3 |
| HAPPSTMNDS | 4 | 7 | 2 | 3 of 3 | 1 | 3 / 3 |
| MASTEK | 4 | 5 | 2 | 3 of 3 | 1 | 3 / 2 |
| GLENMARK | 4 | 16 | 2 | 3 of 3 | 1 | 3 / 3 |
| IKIO | 4 | 7 | 2 | 3 of 3 | 1 | 3 / 3 |
| MATRIMONY | 4 | 9 | 2 | 3 of 3 | 1 | 3 / 3 |
| VOGL | 2 | 8 | 0 | 0 of 0 | 0 | 0 / 0 |

**8 of 10** got the annual-report half (a report read, two or more years of statements shown, and a case); the rest have no annual report on NSE. **7 of 10** have earnings-call transcripts on NSE, and 7 of those got a Promise Ledger with at least one promise; the others file no transcripts, so there is nothing to build a ledger from.

## Cost and speed

Models run on free tiers; the shadow cost is what the same tokens would cost at list prices, logged on every call.

| Task | Calls | From cache | Failed (then retried or fell back) | Tokens in / out (uncached) | Shadow cost | Median latency (uncached) |
|---|---|---|---|---|---|---|
| guidance | 388 | 233 | 3 | 2,187,260 / 60,196 | $0.80 | 1.8 s |
| statements | 247 | 48 | 42 | 752,299 / 192,961 | $0.88 | 3.1 s |
| case | 166 | 13 | 88 | 74,452 / 128,619 | $0.61 | 3.6 s |
| auditor | 78 | 29 | 0 | 389,420 / 13,646 | $0.15 | 1.6 s |
| business | 75 | 30 | 0 | 171,319 / 17,564 | $0.10 | 1.9 s |
| risks | 56 | 31 | 1 | 162,913 / 7,501 | $0.07 | 1.6 s |
| people_card | 19 | 6 | 0 | 51,344 / 5,158 | $0.03 | 2.0 s |

- The Brief and Pulse need no model call: classification, ranking, alerts and results arithmetic are rules and code. People cards are the only push-side model task.
- Dossiers: about $0.062 of shadow cost each across 42 built (including rebuilds; cached answers cost nothing).
