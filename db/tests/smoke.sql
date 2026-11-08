-- Schema smoke test: apply after the migrations; runs in a transaction and rolls back.
\set ON_ERROR_STOP on
begin;

insert into companies (isin, name, sector, is_bank_like, listed_on)
values ('INE040A01034', 'HDFC Bank Ltd', 'Banks', true, '{NSE,BSE}');
insert into company_aliases (isin, kind, value) values ('INE040A01034', 'nse_symbol', 'HDFCBANK');

insert into profiles (is_demo) values (true) returning id as profile_id \gset
insert into holdings (profile_id, isin, weight) values (:'profile_id', 'INE040A01034', 0.06);

insert into events (isin, category, first_seen_at, score, tier)
values ('INE040A01034', 'results', now(), 1.1, 'front') returning id as event_id \gset
insert into filings (isin, exchange, exchange_id, filed_at, subject, category, classified_by, rule_id, event_id)
values ('INE040A01034', 'NSE', 'n-1', now(), 'Financial results for the quarter ended September 30, 2026',
        'results', 'rules', 'results_filing', :event_id);

-- A duplicate exchange id must be rejected by the unique constraint.
savepoint dup;
\set ON_ERROR_STOP off
insert into filings (isin, exchange, exchange_id, filed_at, subject)
values ('INE040A01034', 'NSE', 'n-1', now(), 'same filing again');
\set ON_ERROR_STOP on
rollback to savepoint dup;

insert into documents (isin, doc_type, period) values ('INE040A01034', 'transcript', 'Q2FY27')
returning id as doc_id \gset
insert into doc_pages (document_id, page_no, text, embedding)
values (:doc_id, 1, 'We expect loan growth of 14 to 16 percent in FY27',
        array_fill(0.01::real, array[384])::vector);

select count(*) = 1 as fts_ok from doc_pages where tsv @@ plainto_tsquery('english', 'loan growth') \gset
\if :fts_ok
\else
  \echo 'full-text search failed'
  \quit 3
\endif

select count(*) = 1 as knn_ok from (
  select page_no from doc_pages order by embedding <=> array_fill(0.02::real, array[384])::vector limit 1
) k \gset
\if :knn_ok
\else
  \echo 'vector search failed'
  \quit 3
\endif

insert into jobs (kind, payload) values ('research', '{"isin": "INE040A01034"}');
select count(*) = 1 as claim_ok from (
  select id from jobs where status = 'queued' order by created_at for update skip locked limit 1
) j \gset
\if :claim_ok
\else
  \echo 'job claim failed'
  \quit 3
\endif

\echo 'schema smoke test passed'
rollback;
