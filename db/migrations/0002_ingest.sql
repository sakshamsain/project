-- 0002: what the ingest pipeline, the EOD job and the Brief need beyond 0001.

-- Events are clusters of filings (finn.push.events). The cluster key is the first
-- filing's id, which makes event writes idempotent across retries.
alter table events add column cluster_key text;
alter table events add column family text;
alter table events add column last_filed_at timestamptz;
alter table events add column filing_count int not null default 1;
create unique index events_cluster_key_idx on events (cluster_key);
create index events_family_idx on events (isin, family, first_seen_at desc);
create index events_last_filed_idx on events (last_filed_at desc);

-- What the exchange said, kept beside FINN's own reading of it.
alter table filings add column symbol text;
alter table filings add column summary text;              -- NSE's generated summary, if any

alter table eod_prices add column trades bigint;
alter table eod_prices add column turnover_cr numeric;
create index eod_prices_date_idx on eod_prices (trade_date);

-- Index closes, for relative-to-index rules and abnormal returns.
create table index_prices (
  index_name  text not null,                            -- upper case, e.g. NIFTY 50
  trade_date  date not null,
  close       numeric not null,
  change_pct  numeric,
  primary key (index_name, trade_date)
);

-- Ex-dates that move prices mechanically mute the price rules (finn.push.corporate_actions).
create table corporate_actions (
  isin         text not null references companies (isin),
  ex_date      date not null,
  subject      text not null,
  record_date  date,
  kind         text,
  amount_rs    numeric,
  primary key (isin, ex_date, subject)
);

-- The results calendar.
create table board_meetings (
  isin          text not null references companies (isin),
  meeting_date  date not null,
  purpose       text not null,
  description   text,
  is_results    boolean not null default false,
  announced_at  timestamptz,
  primary key (isin, meeting_date)
);

-- The Brief for one profile and window. Tiers follow finn.push.score.assign_tiers:
-- at most 5 events above 0.75 make the front page, in score order; floor events never
-- fold. test_brief_sql checks these numbers against the Python constants.
create function brief(p_profile uuid, p_from timestamptz, p_to timestamptz)
returns table (
  event_id        bigint,
  isin            text,
  symbol          text,
  company         text,
  category        text,
  family          text,
  stage           text,
  headline        text,
  why_it_matters  text,
  score           double precision,
  tier            text,
  first_seen_at   timestamptz,
  last_filed_at   timestamptz,
  filing_count    int,
  score_breakdown jsonb,
  enrichment      jsonb
)
language sql stable
as $$
  with items as (
    select e.*,
           coalesce((e.score_breakdown ->> 'floor_applied')::boolean, false) as is_floor
    from events e
    join holdings h on h.isin = e.isin and h.profile_id = p_profile
    where coalesce(e.last_filed_at, e.first_seen_at) >= p_from
      and e.first_seen_at < p_to
  ),
  ranked as (
    select i.*,
           count(*) filter (where i.score >= 0.75)
             over (order by i.score desc nulls last, i.first_seen_at desc, i.id
                   rows between unbounded preceding and current row) as front_rank
    from items i
  )
  select r.id, r.isin,
         (select a.value from company_aliases a
           where a.isin = r.isin and a.kind = 'nse_symbol' and a.valid_to is null
           order by a.valid_from desc limit 1),
         c.name, r.category, r.family, r.stage, r.headline, r.why_it_matters, r.score,
         case
           when r.score >= 0.75 and r.front_rank <= 5 then 'front'
           when r.score >= 0.35 or r.is_floor then 'oneliner'
           else 'folded'
         end,
         r.first_seen_at, r.last_filed_at, r.filing_count, r.score_breakdown, r.enrichment
  from ranked r
  join companies c on c.isin = r.isin
  order by r.score desc nulls last, r.first_seen_at desc
$$;
