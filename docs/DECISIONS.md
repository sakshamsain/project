# Decision records

Short records of choices that shape the build. Newest last.

## 001 · Installable web app over a native app
A PWA opens from one link on any phone; Expo Go or TestFlight would add reviewer
friction. Cost: iPhones allow web push only after "Add to Home Screen", so the app ships
an install hint and an in-app inbox that works without push.

## 002 · Workers write, the app only reads
Python workers on Modal fill Postgres; Next.js on Vercel reads it. No request from the
phone waits on a cold Python container. Research requests become job rows that a worker
claims with `FOR UPDATE SKIP LOCKED`; progress streams back to the page.

## 003 · Code computes every number
Models extract, classify and phrase. Ratios, QoQ/YoY, margins and scores are code with
unit tests. A results card that fails its accounting checks shows "Numbers need a look"
and the filing link instead of a figure.

## 004 · Rules before models
Exchange subjects are regular enough for regex rules to classify most filings at zero
cost (`finn/push/rules.yaml`). Only unmatched filings reach the small model. Rule
coverage is measured on 30 days of real filings before any prompt is written.

## 005 · Closed-book grounding with quote checks
Pull-side prompts may use only supplied excerpts. Every extracted promise must quote the
transcript verbatim, checked mechanically, or it is dropped. Every sentence cites a page
or a computed fact.

## 006 · Free-tier routing by tier
Tiers, not model names, appear in code: T0 code, T1 small (Groq), T2 long-context reader
(Gemini Flash-Lite, escalating to Flash), T3 strong (Gemini Flash). IDs are pinned in
`models.yaml`. Every call records a shadow cost at paid list prices to show efficiency.

## 007 · Neon's S3-compatible storage instead of Cloudflare R2
PDFs and other blobs go to Neon's object storage, keyed by sha256, so storage and the
database sit with one provider and one set of credentials. Postgres holds extracted
text only, which keeps the database well inside the free plan's 1 GB.

## 008 · ISIN as the canonical key
NSE symbols change (renames, demergers); ISIN does not. Symbols, BSE codes, Yahoo
tickers and Screener slugs are aliases with validity dates.

## 009 · NSE first, BSE later
The Day-0 spike from Modal reached NSE's RSS feeds, its announcements API, the bhavcopy
and delivery files, Screener and Yahoo. BSE's API answered 403, matching the `bse`
client's warning that BSE is changing endpoints. Ingestion builds on NSE; BSE returns as
a second source only once a working endpoint is confirmed.

## 010 · Pin models that answer, not the newest
On 8 Nov the newest free Flash models (3.7, 3.8) returned 503 "high demand" while
3.5 Flash-Lite and 3.6 Flash answered in under 4 s. A demo that fails under load is
worse than an older model, so tiers pin the reliable ones and list newer ones as
candidates to re-test.

## 011 · Migrations over Neon's HTTPS endpoint
`finn.core.migrate` applies each file once inside a transaction, records a checksum and
refuses edited files. It talks to Neon over HTTPS, so it works where raw TCP to Postgres
is blocked; CI applies the same files with psql against pgvector.
