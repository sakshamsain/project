-- FINN schema v1. Source of truth for both runtimes: Python workers write, Next.js reads.
-- Postgres 16+ with pgvector. Migrations are append-only: never edit a shipped file.

create extension if not exists vector;

-- Reference ---------------------------------------------------------------

create table companies (
  isin          text primary key,
  name          text not null,
  sector        text,
  industry      text,
  is_bank_like  boolean not null default false,  -- banks and NBFCs show PPOP, not EBITDA
  listed_on     text[] not null default '{}',     -- {NSE,BSE}
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create table company_aliases (
  isin        text not null references companies (isin) on delete cascade,
  kind        text not null check (kind in ('nse_symbol', 'bse_code', 'yahoo', 'screener')),
  value       text not null,
  valid_from  date not null default '1900-01-01',
  valid_to    date,                                -- null means current
  primary key (kind, value, valid_from)
);
create index company_aliases_isin_idx on company_aliases (isin);

-- Profiles and holdings (anonymous, device-scoped) -------------------------

create table profiles (
  id            uuid primary key default gen_random_uuid(),
  is_demo       boolean not null default false,
  created_at    timestamptz not null default now(),
  last_seen_at  timestamptz
);

create table holdings (
  profile_id  uuid not null references profiles (id) on delete cascade,
  isin        text not null references companies (isin),
  weight      numeric(6, 4),                      -- share of the book, optional
  added_at    timestamptz not null default now(),
  primary key (profile_id, isin)
);

-- Raw layer (immutable) ----------------------------------------------------

create table raw_records (
  id          bigserial primary key,
  source      text not null,                      -- nse_rss, nse_api, bse_api, bhavcopy, screener
  source_key  text not null,                      -- idempotency key within the source
  payload     jsonb not null,
  fetched_at  timestamptz not null default now(),
  unique (source, source_key)
);

create table blobs (
  sha256        text primary key,
  bytes         bigint not null,
  content_type  text,
  storage_key   text not null,                    -- key in object storage
  source_url    text,
  created_at    timestamptz not null default now()
);

-- Events and filings -------------------------------------------------------

create table events (
  id              bigserial primary key,
  isin            text not null references companies (isin),
  category        text not null,
  attributes      jsonb not null default '{}',
  stage           text,
  first_seen_at   timestamptz not null,
  updated_at      timestamptz not null default now(),
  score           double precision,
  score_breakdown jsonb,                          -- powers "why is this here?"
  tier            text check (tier in ('front', 'oneliner', 'folded')),
  headline        text,
  why_it_matters  text,
  enrichment      jsonb not null default '{}'
);
create index events_isin_time_idx on events (isin, first_seen_at desc);
create index events_time_idx on events (first_seen_at desc);

create table filings (
  id                 bigserial primary key,
  isin               text not null references companies (isin),
  exchange           text not null check (exchange in ('NSE', 'BSE')),
  exchange_id        text not null,
  filed_at           timestamptz not null,
  subject            text not null,
  exchange_category  text,
  body_text          text,
  attachment_url     text,
  attachment_sha     text references blobs (sha256),
  category           text,
  attributes         jsonb not null default '{}',
  classified_by      text check (classified_by in ('rules', 'model', 'human')),
  rule_id            text,
  confidence         double precision,
  event_id           bigint references events (id),
  duplicate_of       bigint references filings (id),  -- the NSE copy of a BSE filing, or vice versa
  created_at         timestamptz not null default now(),
  unique (exchange, exchange_id)
);
create index filings_isin_time_idx on filings (isin, filed_at desc);
create index filings_time_idx on filings (filed_at desc);
create index filings_event_idx on filings (event_id);

-- Prices and anomalies -----------------------------------------------------

create table eod_prices (
  isin          text not null references companies (isin),
  trade_date    date not null,
  open          numeric,
  high          numeric,
  low           numeric,
  close         numeric not null,
  prev_close    numeric,
  volume        bigint not null,
  delivery_qty  bigint,
  delivery_pct  numeric,
  source        text not null,                    -- bhavcopy, yfinance
  primary key (isin, trade_date)
);

create table anomalies (
  id               bigserial primary key,
  isin             text not null references companies (isin),
  trade_date       date not null,
  kind             text not null
                   check (kind in ('volume_multiple', 'price_move', 'sigma_move', 'delivery_spike')),
  value            double precision not null,
  threshold        double precision not null,
  zscore           double precision,
  linked_event_id  bigint references events (id), -- null means "No filing found"
  created_at       timestamptz not null default now(),
  unique (isin, trade_date, kind)
);

-- Documents and fundamentals -----------------------------------------------

create table documents (
  id              bigserial primary key,
  isin            text not null references companies (isin),
  doc_type        text not null
                  check (doc_type in ('annual_report', 'transcript', 'results', 'presentation', 'other')),
  period          text,                           -- FY26, Q2FY27
  published_on    date,
  source_url      text,
  sha256          text references blobs (sha256),
  pages           int,
  has_text_layer  boolean,
  parsed_at       timestamptz,
  unique (isin, doc_type, sha256)
);

create table doc_pages (
  document_id  bigint not null references documents (id) on delete cascade,
  page_no      int not null,
  text         text not null,
  tsv          tsvector generated always as (to_tsvector('english', text)) stored,
  embedding    vector(384),                       -- bge-small-en-v1.5
  primary key (document_id, page_no)
);
create index doc_pages_tsv_idx on doc_pages using gin (tsv);
create index doc_pages_embedding_idx on doc_pages using hnsw (embedding vector_cosine_ops);

create table financials (
  isin           text not null references companies (isin),
  period         text not null,                   -- Q2FY27, FY26
  period_type    text not null check (period_type in ('Q', 'H', '9M', 'FY')),
  basis          text not null check (basis in ('consolidated', 'standalone')),
  metric         text not null,                   -- revenue, ebitda, pbt, pat, ppop, nii
  value_cr       numeric not null,                -- INR crore
  source         text not null check (source in ('xbrl', 'pdf', 'screener')),
  source_doc_id  bigint references documents (id),
  page           int,
  primary key (isin, period, basis, metric, source)
);

create table guidance (
  id             bigserial primary key,
  isin           text not null references companies (isin),
  thread_id      bigint,
  metric         text not null,
  target_period  text,
  value_low      numeric,
  value_high     numeric,
  unit           text,
  qualifier      text,
  quote          text not null,                   -- verified as an exact substring before insert
  speaker        text,
  document_id    bigint not null references documents (id),
  page           int,
  call_date      date,
  status         text check (status in
                   ('delivered', 'missed', 'on_track', 'too_early', 'not_measurable', 'dropped')),
  created_at     timestamptz not null default now()
);
create index guidance_isin_thread_idx on guidance (isin, thread_id);

create table dossier_sections (
  isin            text not null references companies (isin),
  section         text not null,
  docset_hash     text not null,
  prompt_version  text not null,
  body            jsonb not null,
  built_at        timestamptz not null default now(),
  primary key (isin, section, docset_hash, prompt_version)
);

-- Alerts, notifications and feedback ---------------------------------------

create table alert_rules (
  id          bigserial primary key,
  profile_id  uuid not null references profiles (id) on delete cascade,
  isin        text references companies (isin),   -- null applies to every holding
  kind        text not null check (kind in
                ('category', 'volume_multiple', 'price_move', 'sigma_move',
                 'relative_to_index', 'delivery_spike')),
  params      jsonb not null default '{}',
  enabled     boolean not null default true,
  created_at  timestamptz not null default now()
);

create table push_subscriptions (
  id          bigserial primary key,
  profile_id  uuid not null references profiles (id) on delete cascade,
  endpoint    text not null unique,
  p256dh      text not null,
  auth        text not null,
  created_at  timestamptz not null default now()
);

create table notifications (
  id          bigserial primary key,
  profile_id  uuid not null references profiles (id) on delete cascade,
  dedupe_key  text not null,                      -- one push per event, whichever exchange filed first
  event_id    bigint references events (id),
  anomaly_id  bigint references anomalies (id),
  channel     text not null check (channel in ('push', 'inbox')),
  status      text not null default 'queued' check (status in ('queued', 'sent', 'failed', 'held')),
  sent_at     timestamptz,
  unique (profile_id, dedupe_key, channel)
);

create table feedback (
  id          bigserial primary key,
  profile_id  uuid not null references profiles (id) on delete cascade,
  event_id    bigint not null references events (id),
  action      text not null check (action in ('got_it', 'less_like_this', 'opened')),
  created_at  timestamptz not null default now()
);

-- Operations ---------------------------------------------------------------

create table jobs (
  id           bigserial primary key,
  kind         text not null,                     -- research, ingest, eod, replay
  payload      jsonb not null default '{}',
  status       text not null default 'queued'
               check (status in ('queued', 'running', 'done', 'failed')),
  attempts     int not null default 0,
  progress     jsonb not null default '{}',       -- streamed to the dossier page
  error        text,
  profile_id   uuid references profiles (id),
  created_at   timestamptz not null default now(),
  started_at   timestamptz,
  finished_at  timestamptz
);
-- Workers claim with: select ... where status = 'queued' order by created_at
--                     for update skip locked limit 1
create index jobs_queue_idx on jobs (created_at) where status = 'queued';

create table llm_calls (
  id               bigserial primary key,
  task             text not null,
  tier             text not null,
  provider         text not null,
  model            text not null,
  prompt_version   text not null,
  input_hash       text not null,
  tokens_in        int not null default 0,
  tokens_out       int not null default 0,
  latency_ms       int,
  cache_hit        boolean not null default false,
  shadow_cost_usd  numeric(12, 6) not null default 0,  -- tokens at the paid list price
  ok               boolean not null default true,
  error            text,
  created_at       timestamptz not null default now()
);
create index llm_calls_task_time_idx on llm_calls (task, created_at desc);

create table llm_cache (
  key         text primary key,                   -- sha256(task | prompt_version | model | input_hash)
  output      jsonb not null,
  created_at  timestamptz not null default now()
);

create table source_health (
  source                text primary key,
  last_ok_at            timestamptz,
  last_error_at         timestamptz,
  last_error            text,
  consecutive_failures  int not null default 0
);
