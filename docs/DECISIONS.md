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

## 012 · psycopg on the worker, HTTPS on the web
The worker runs on Modal, which can open TCP to Neon, so it uses psycopg against Neon's
direct endpoint (prepared statements off, COPY for bulk upserts). The web app reads over
Neon's HTTPS driver with a separate role, `finn_web`, that can read everything but write
only profiles, holdings, alert rules, push subscriptions and feedback. Database tests run
on a real Postgres with pgvector, locally and in CI, from the same migration files.

## 013 · Anomalies stored at floor limits, filtered per profile
The EOD job stores every hit at or above fixed floors (1.5x volume, 3% price, 2.0 sigma,
1.3x delivery). Each profile's own limits, at or above the floors, filter at read time,
so changing a setting never needs a recompute.

## 014 · Events are rebuilt, not patched
When rules or clustering change, `rebuild` re-reads every rules-classified filing,
drops all events and replays the filings day by day through the live code path, then the
EOD rescan restores anomaly links and price reactions. A test checks that a replay
reproduces live clustering exactly. Model and human labels are never overwritten.

## 015 · Headlines from the exchange's own words first
NSE describes each attachment in one sentence and sometimes summarises it. Stripping the
"has informed the Exchange regarding" frame gives a usable headline for most filings, and
a results press release lends its title (which leads with the numbers) to its results
event. Models will rewrite only front-page headlines, from the filing alone.

## 016 · People cards quote the filing
SEBI makes a company publish a brief profile of each director or KMP it appoints. The
people card is that profile, quoted: a model picks the people and the sentences,
`verify_quote` keeps only sentences really in the PDF (the page comes from the text), and
a name not in the filing drops the person. For more, the card offers a LinkedIn search
link; FINN does not fetch or scrape profiles.

## 017 · The ledger checks only what the filings can measure
A promise is checked against quarterly XBRL figures only when it is company-wide, in
rupees, names a measure code can compute (EBIT is not EBITDA), and states figures that
appear in the quote. Constant-currency growth, segment targets, adjusted figures, AUM,
order inflow and hiring are kept, quoted and tracked from call to call, marked "not in
the filings" with the reason. A wrong tick is worse than an honest "cannot check".

## 018 · Research on request: a job row, a ping, and a poll as backstop
The app records a request as a `jobs` row and pings a token-protected Modal endpoint,
which starts the build at once; the 5-minute poll claims anything the ping missed (FOR
UPDATE SKIP LOCKED). Progress is written to the row and shown on the page. Ten new
ledgers per device per day; built ledgers are open to everyone.

## 019 · Accounts are optional and live in our own database
Better Auth (email and password) runs inside the Next.js app; users and sessions sit in
Postgres (migration 0006), so there is no outside identity service to configure. A
device without an account keeps an anonymous portfolio; signing up moves it into the
account, which then follows the user to any device; a profile that belongs to an account
is never shown to a signed-out visitor on the same device. Not yet: email verification
and password reset, which need an email sender.

## 020 · Charts are hand-built SVG and interactive by default
One measure per chart: price, with volume in its own strip; revenue (or NII) and net
profit as two charts, never a second axis. Every chart has a crosshair or per-mark
tooltip, keyboard reading and a table view; filings sit on the price line and open on
tap. The chart colour was run through the dataviz palette checks for both surfaces;
dark mode uses its own darker violet step because the lighter one failed the band.

## 021 · Annual reports are read by what is on the page
Layouts differ by company (HCLTech's PDF puts statement titles at the bottom of the
page, Dixon prints in lakh with the rupee sign as a stray glyph, Bajaj Finance's auditor
heading is an image), so parts are found by content: a statement is a page with its title
near the top or bottom, dozens of figures and the lines every such statement has; it ends
at its closing line or where another statement starts. Consolidated statements are used
when filed. The unit is read from the words on the page, never assumed. Ten reports from
five companies were located correctly before any code shipped, and are kept as fixtures.

## 022 · Statement figures: the model copies, code places and adds
A figure counts only when it is one of the first two figures in its label's row, current
year first, so a figure from the next row, a swapped column or a wide equity table is
refused. Accounting identities gate each year (cash flows add up to the change in cash;
PBT less tax is profit), and full-year revenue and profit are checked against the four
quarterly XBRL filings: on all five research companies FY26 matched exactly. Lines that
are summed (capex, dividends, buybacks) need both sides to agree: code scans for them
too, withholds a sum if the model missed a line, and drops a model line code does not
recognise (TCS's advances for leased assets are not capex). A weak answer is asked once
more of the stronger model, which must not be served the weaker model's cached answer.

## 023 · Bull vs bear only from checked facts
The case is written from a numbered list of facts code already checked or computed:
figures from the Cash table, promises with their ledger status, quotes verified in the
annual report. Each point cites its facts; a number in a point must appear in a cited
fact, and advice words fail the house style. Key audit matters are labelled as where the
auditor looked hardest, not findings, and a lender's operating cash flow is left out
because it tracks lending rather than health. Both sides are always shown together.

## 024 · Keep only the pages read, and show them
An annual report is 300-600 pages; FINN stores the 15-25 it reads, which keeps the
database small enough for on-demand research on any ticker. Every citation opens FINN's
copy of the page with the quote marked, and links the PDF at that page; transcript
quotes in the ledger use the same view.

