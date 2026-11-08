-- 0003: the research side (documents, guidance checks) and a grant for test alerts.

-- One row per source file; the URL is how FINN cites it.
alter table documents add column title text;
alter table documents add column filed_at timestamptz;
alter table documents add column event_period text;      -- the quarter a call discusses, Q2FY27
create unique index documents_source_url_idx on documents (source_url) where source_url is not null;
create index documents_isin_type_idx on documents (isin, doc_type, filed_at desc);

-- What was promised, in a form code can check, and what code found.
alter table guidance add column metric_key text;         -- revenue, ebitda_margin, pat, capex, ...
alter table guidance add column kind text check (kind in ('growth', 'margin', 'level', 'qualitative'));
alter table guidance add column period_start date;
alter table guidance add column period_end date;
alter table guidance add column actual_value numeric;
alter table guidance add column actual_note text;        -- what was compared, in words
alter table guidance add column checked_at timestamptz;
alter table guidance add column extraction jsonb;        -- the model's raw item, kept for audit
create unique index guidance_dedupe_idx on guidance (document_id, md5(quote));

-- The web app records a test alert so it can allow one every 30 seconds.
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'finn_web') then
    grant insert on notifications to finn_web;
  end if;
end
$$;
