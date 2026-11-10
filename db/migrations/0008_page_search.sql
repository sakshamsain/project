-- 0008: full-text search over the pages FINN keeps, for questions asked of a company's
-- filings. English stemming; the index is what retrieval reads.
alter table doc_pages
  add column if not exists tsv tsvector
  generated always as (to_tsvector('english', coalesce(text, ''))) stored;

create index if not exists doc_pages_tsv on doc_pages using gin (tsv);
