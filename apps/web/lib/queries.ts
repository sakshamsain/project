// Every query the app runs. Tiers come from the brief() SQL function, which follows the
// worker's scoring rules; this file only reads.
import type { PeopleCardData } from "@/components/PeopleCard";
import type { ResultsCardData } from "@/components/ResultsCard";
import { query } from "./db";

export type Contributions = { category: number; size: number; reaction: number; novelty: number };

export type Breakdown = {
  base: number;
  user_weight: number;
  size: number;
  reaction: number;
  novelty: number;
  floor_applied: boolean;
  score: number;
  contributions?: Contributions;
  is_first_filing?: boolean;
  is_restatement?: boolean;
  representative?: string;
};

export type Reaction = {
  trade_date: string;
  return_pct: number | null;
  index_return_pct: number | null;
  abnormal_return_pct: number | null;
  volume_multiple: number | null;
  volume_z: number | null;
};

export type Tier = "front" | "oneliner" | "folded";

export type BriefRow = {
  event_id: string;
  isin: string;
  symbol: string | null;
  company: string;
  category: string;
  family: string | null;
  stage: string | null;
  headline: string | null;
  why_it_matters: string | null;
  score: number;
  tier: Tier;
  first_seen_at: string;
  last_filed_at: string | null;
  filing_count: number;
  score_breakdown: Breakdown | null;
  enrichment: {
    reaction?: Reaction;
    results_card?: ResultsCardData;
    people_card?: PeopleCardData;
    ledger?: LedgerCheck;
  } | null;
  attachment_url: string | null;
};

// The bridge: a results event's check against the company's Promise Ledger, made by
// the worker when the results were read (or the ledger's latest statuses, for results
// that arrived before the check existed).
export type LedgerPromise = {
  id: number;
  metric: string;
  metric_key: string | null;
  period: string | null;
  status: "delivered" | "missed" | "on_track" | "off_track";
  note: string | null;
  quote: string;
  page: number | null;
  document_id: number;
  call_date: string;
};

export type LedgerCheck = {
  counts: Record<string, number>;
  measured: LedgerPromise[];
  changes: { id: number; metric: string; period: string | null; was: string | null }[];
  checked_at: string;
};

export async function getLedgerNow(isin: string): Promise<LedgerCheck | null> {
  const rows = await query<LedgerPromise & { counts: Record<string, number>; checked_at: string }>(
    `with c as (select jsonb_object_agg(status, n) as counts, max(checked_at)::text as checked_at
                  from (select status, count(*)::int as n, max(checked_at) as checked_at
                          from guidance where isin = $1 group by status) s)
     select g.id::int as id, g.metric, g.metric_key, g.period_label as period, g.status,
            g.actual_note as note,
            g.quote, g.page, g.document_id::int as document_id, g.call_date::text as call_date,
            c.counts, c.checked_at
       from guidance g, c
      where g.isin = $1 and g.status in ('delivered', 'missed', 'on_track', 'off_track')
      order by g.call_date desc, g.id limit 6`,
    [isin],
  );
  if (rows.length === 0) return null;
  return {
    counts: rows[0].counts,
    checked_at: rows[0].checked_at,
    changes: [],
    measured: rows.map(({ counts: _c, checked_at: _t, ...p }) => p),
  };
}

export async function getBrief(profileId: string, from: Date, to: Date): Promise<BriefRow[]> {
  return query<BriefRow>(
    `select b.event_id::text as event_id, b.isin, b.symbol, b.company, b.category, b.family,
            b.stage, b.headline, b.why_it_matters, b.score, b.tier,
            b.first_seen_at::text as first_seen_at, b.last_filed_at::text as last_filed_at,
            b.filing_count, b.score_breakdown, b.enrichment,
            (select f.attachment_url from filings f
              where f.event_id = b.event_id
              order by (f.exchange || ':' || f.exchange_id = b.score_breakdown ->> 'representative') desc,
                       f.filed_at
              limit 1) as attachment_url
       from brief($1, $2, $3) b`,
    [profileId, from.toISOString(), to.toISOString()],
  );
}

export async function countHoldings(profileId: string): Promise<number> {
  const [r] = await query<{ n: number }>(
    "select count(*)::int as n from holdings where profile_id = $1",
    [profileId],
  );
  return r?.n ?? 0;
}

export type Meeting = {
  symbol: string;
  company: string;
  meeting_date: string;
  description: string | null;
  is_results: boolean;
};

export async function getComingUp(profileId: string, days = 21): Promise<Meeting[]> {
  return query<Meeting>(
    `select a.value as symbol, c.name as company, m.meeting_date::text as meeting_date,
            m.description, m.is_results
       from board_meetings m
       join holdings h on h.isin = m.isin and h.profile_id = $1
       join companies c on c.isin = m.isin
       join company_aliases a on a.isin = m.isin and a.kind = 'nse_symbol' and a.valid_to is null
      where m.meeting_date >= (now() at time zone 'Asia/Kolkata')::date
        and m.meeting_date <= (now() at time zone 'Asia/Kolkata')::date + $2::int
      order by m.meeting_date, a.value`,
    [profileId, days],
  );
}

// ---------- alert thresholds ----------

export type Thresholds = { volume: number; price: number; sigma: number; delivery: number };

export const DEFAULT_THRESHOLDS: Thresholds = { volume: 2.0, price: 5.0, sigma: 2.5, delivery: 1.5 };

// The worker stores anomalies at these floors (finn.push.eod.FLOOR_THRESHOLDS); a
// profile can only ask for thresholds at or above them.
export const FLOORS: Thresholds = { volume: 1.5, price: 3.0, sigma: 2.0, delivery: 1.3 };

const RULE_KIND: Record<keyof Thresholds, string> = {
  volume: "volume_multiple",
  price: "price_move",
  sigma: "sigma_move",
  delivery: "delivery_spike",
};

export async function getThresholds(profileId: string): Promise<Thresholds> {
  const rows = await query<{ kind: string; value: number | null }>(
    `select kind, (params ->> 'value')::float8 as value from alert_rules
      where profile_id = $1 and isin is null and enabled`,
    [profileId],
  );
  const out = { ...DEFAULT_THRESHOLDS };
  for (const key of Object.keys(RULE_KIND) as (keyof Thresholds)[]) {
    const r = rows.find((x) => x.kind === RULE_KIND[key]);
    if (r?.value != null && Number.isFinite(r.value)) out[key] = Math.max(FLOORS[key], r.value);
  }
  return out;
}

export async function saveThresholds(profileId: string, t: Thresholds): Promise<void> {
  for (const key of Object.keys(RULE_KIND) as (keyof Thresholds)[]) {
    await query("delete from alert_rules where profile_id = $1 and isin is null and kind = $2", [
      profileId,
      RULE_KIND[key],
    ]);
    await query(
      "insert into alert_rules (profile_id, kind, params) values ($1, $2, jsonb_build_object('value', $3::float8))",
      [profileId, RULE_KIND[key], Math.max(FLOORS[key], t[key])],
    );
  }
}

// ---------- pulse: end-of-day moves ----------

export type Hit = { kind: string; value: number; threshold: number; zscore: number | null };

export type Move = {
  isin: string;
  symbol: string;
  company: string;
  trade_date: string;
  close: number | null;
  return_pct: number | null;
  index_change_pct: number | null;
  linked_event_id: string | null;
  linked_headline: string | null;
  linked_category: string | null;
  hits: Hit[];
};

type MoveRow = Omit<Move, "hits"> & Hit;

export function passes(h: Hit, t: Thresholds, hits: Hit[]): boolean {
  switch (h.kind) {
    case "volume_multiple":
      return h.value >= t.volume;
    case "price_move":
      return Math.abs(h.value) >= t.price;
    case "sigma_move":
      return Math.abs(h.zscore ?? 0) >= t.sigma;
    case "delivery_spike": {
      const usual = h.threshold / FLOORS.delivery; // stored threshold = floor x usual share
      const volumeOk = hits.some((x) => x.kind === "volume_multiple" && x.value >= t.volume);
      return volumeOk && usual > 0 && h.value / usual >= t.delivery;
    }
    default:
      return false;
  }
}

export async function getPulse(profileId: string, t: Thresholds, sessions = 5) {
  const rows = await query<MoveRow>(
    `with days as (select distinct trade_date from eod_prices order by trade_date desc limit $2)
     select a.isin, a.trade_date::text as trade_date, a.kind, a.value, a.threshold, a.zscore,
            a.linked_event_id::text as linked_event_id, c.name as company,
            coalesce((select ca.value from company_aliases ca
                       where ca.isin = a.isin and ca.kind = 'nse_symbol' and ca.valid_to is null
                       limit 1), a.isin) as symbol,
            p.close::float8 as close,
            round(((p.close / nullif(p.prev_close, 0)) - 1) * 100, 2)::float8 as return_pct,
            ip.change_pct::float8 as index_change_pct,
            e.headline as linked_headline, e.category as linked_category
       from anomalies a
       join holdings h on h.isin = a.isin and h.profile_id = $1
       join companies c on c.isin = a.isin
       left join eod_prices p on p.isin = a.isin and p.trade_date = a.trade_date
       left join events e on e.id = a.linked_event_id
       left join index_prices ip on ip.index_name = 'NIFTY 50' and ip.trade_date = a.trade_date
      where a.trade_date in (select trade_date from days)
      order by a.trade_date desc, symbol`,
    [profileId, sessions],
  );
  const days = await query<{ d: string }>(
    "select distinct trade_date::text as d from eod_prices order by d desc limit $1",
    [sessions],
  );
  const grouped = new Map<string, Move>();
  for (const r of rows) {
    const key = `${r.trade_date}|${r.isin}`;
    let m = grouped.get(key);
    if (!m) {
      const { kind, value, threshold, zscore, ...rest } = r;
      void kind;
      void value;
      void threshold;
      void zscore;
      m = { ...rest, hits: [] };
      grouped.set(key, m);
    }
    m.hits.push({ kind: r.kind, value: r.value, threshold: r.threshold, zscore: r.zscore });
  }
  const moves = [...grouped.values()]
    .map((m) => ({ ...m, hits: m.hits.filter((h) => passes(h, t, m.hits)) }))
    .filter((m) => m.hits.length > 0);
  return { days: days.map((d) => d.d), moves };
}

// ---------- event and company pages ----------

export type EventDetail = BriefRow & { tier: Tier };

export type Filing = {
  subject: string;
  body_text: string | null;
  summary: string | null;
  filed_at: string;
  attachment_url: string | null;
  category: string | null;
  rule_id: string | null;
  classified_by: string | null;
};

export async function getEvent(id: string) {
  if (!/^\d+$/.test(id)) return null;
  const [e] = await query<EventDetail>(
    `select e.id::text as event_id, e.isin, c.name as company,
            (select a.value from company_aliases a
              where a.isin = e.isin and a.kind = 'nse_symbol' and a.valid_to is null limit 1) as symbol,
            e.category, e.family, e.stage, e.headline, e.why_it_matters, e.score, e.tier,
            e.first_seen_at::text as first_seen_at, e.last_filed_at::text as last_filed_at,
            e.filing_count, e.score_breakdown, e.enrichment, null as attachment_url
       from events e join companies c on c.isin = e.isin where e.id = $1`,
    [id],
  );
  if (!e) return null;
  const filings = await query<Filing>(
    `select subject, body_text, summary, filed_at::text as filed_at, attachment_url, category,
            rule_id, classified_by
       from filings where event_id = $1 order by filed_at`,
    [id],
  );
  const hits = await query<Hit & { trade_date: string }>(
    `select kind, value, threshold, zscore, trade_date::text as trade_date
       from anomalies where linked_event_id = $1 order by trade_date, kind`,
    [id],
  );
  return { event: e, filings, hits };
}

export type CompanyEvent = {
  event_id: string;
  category: string;
  stage: string | null;
  headline: string | null;
  score: number;
  tier: Tier;
  first_seen_at: string;
  filing_count: number;
};

export async function getCompany(symbol: string, profileId: string) {
  const [c] = await query<{ isin: string; name: string; industry: string | null; symbol: string }>(
    `select c.isin, c.name, c.industry, a.value as symbol
       from company_aliases a join companies c on c.isin = a.isin
      where a.kind = 'nse_symbol' and a.value = upper($1) and a.valid_to is null limit 1`,
    [symbol],
  );
  if (!c) return null;
  const [bars, events, meetings, held, marks, quarters] = await Promise.all([
    query<{ trade_date: string; close: number; prev_close: number | null; volume: number }>(
      `select trade_date::text as trade_date, close::float8 as close,
              prev_close::float8 as prev_close, volume::float8 as volume
         from eod_prices where isin = $1 order by trade_date desc limit 260`,
      [c.isin],
    ),
    query<CompanyEvent>(
      `select id::text as event_id, category, stage, headline, score, tier,
              first_seen_at::text as first_seen_at, filing_count
         from events where isin = $1 and first_seen_at > now() - interval '60 days'
        order by first_seen_at desc limit 60`,
      [c.isin],
    ),
    query<{ meeting_date: string; description: string | null; is_results: boolean }>(
      `select meeting_date::text as meeting_date, description, is_results from board_meetings
        where isin = $1 and meeting_date >= (now() at time zone 'Asia/Kolkata')::date
        order by meeting_date limit 3`,
      [c.isin],
    ),
    query("select 1 from holdings where profile_id = $1 and isin = $2", [profileId, c.isin]),
    // A filing after the 15:30 close moves the next session, hence the 8h30m shift.
    query<{ id: string; d: string; headline: string | null; tier: "front" | "oneliner"; category: string; stage: string | null }>(
      `select id::text, (((first_seen_at at time zone 'Asia/Kolkata') + interval '8 hours 30 minutes')::date)::text as d,
              headline, tier, category, stage
         from events
        where isin = $1 and tier in ('front', 'oneliner') and first_seen_at > now() - interval '400 days'
        order by first_seen_at`,
      [c.isin],
    ),
    query<{ period: string; metric: string; value: number; basis: string }>(
      `with b as (
         select case when bool_or(basis = 'consolidated') then 'consolidated' else 'standalone' end as basis
           from financials where isin = $1 and period_type = 'Q'
       )
       select f.period, f.metric, f.value_cr::float8 as value, f.basis
         from financials f, b
        where f.isin = $1 and f.period_type = 'Q' and f.basis = b.basis
          and f.metric in ('revenue', 'nii', 'pat')`,
      [c.isin],
    ),
  ]);
  return {
    company: c,
    bars: bars.reverse(),
    events,
    meetings,
    held: held.length > 0,
    marks,
    quarters,
  };
}

// ---------- portfolio ----------

export type Holding = {
  isin: string;
  symbol: string;
  name: string;
  close: number | null;
  return_pct: number | null;
  trade_date: string | null;
};

export async function getHoldings(profileId: string): Promise<Holding[]> {
  return query<Holding>(
    `select h.isin, coalesce(a.value, h.isin) as symbol, c.name, p.close::float8 as close,
            round(((p.close / nullif(p.prev_close, 0)) - 1) * 100, 2)::float8 as return_pct,
            p.trade_date::text as trade_date
       from holdings h
       join companies c on c.isin = h.isin
       left join lateral (select value from company_aliases
                           where isin = h.isin and kind = 'nse_symbol' and valid_to is null
                           limit 1) a on true
       left join lateral (select close, prev_close, trade_date from eod_prices
                           where isin = h.isin order by trade_date desc limit 1) p on true
      where h.profile_id = $1
      order by symbol`,
    [profileId],
  );
}

export async function searchCompanies(q: string) {
  const s = q.trim().slice(0, 40);
  if (!s) return [];
  return query<{ symbol: string; name: string; isin: string }>(
    `select a.value as symbol, c.name, c.isin
       from company_aliases a join companies c on c.isin = a.isin
      where a.kind = 'nse_symbol' and a.valid_to is null
        and (a.value ilike $1 || '%' or c.name ilike '%' || $1 || '%')
      order by (a.value = upper($1)) desc, (a.value ilike $1 || '%') desc, length(a.value), a.value
      limit 12`,
    [s],
  );
}

// ---------- status ----------

export async function getStatus() {
  const sources = await query<{
    source: string;
    last_ok_at: string | null;
    last_error_at: string | null;
    last_error: string | null;
    consecutive_failures: number;
  }>(
    `select source, last_ok_at::text as last_ok_at, last_error_at::text as last_error_at,
            last_error, consecutive_failures from source_health order by source`,
  );
  const [counts] = await query<{
    filings: number;
    events: number;
    companies: number;
    anomalies: number;
    last_filing: string | null;
    last_bar: string | null;
    first_filing: string | null;
    llm_calls: number;
    llm_cost: number;
  }>(
    `select (select count(*) from filings)::int as filings,
            (select count(*) from events)::int as events,
            (select count(*) from companies)::int as companies,
            (select count(*) from anomalies)::int as anomalies,
            (select max(filed_at) from filings)::text as last_filing,
            (select min(filed_at) from filings)::text as first_filing,
            (select max(trade_date) from eod_prices)::text as last_bar,
            (select count(*) from llm_calls)::int as llm_calls,
            (select coalesce(sum(shadow_cost_usd), 0) from llm_calls)::float8 as llm_cost`,
  );
  return { sources, counts };
}
