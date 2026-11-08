// The Promise Ledger as the worker stored it: dossier_sections (one per company) and
// guidance rows with their checks. Every figure here was computed by the worker.
import { query } from "./db";

export type LedgerStatus =
  | "delivered"
  | "missed"
  | "on_track"
  | "off_track"
  | "too_early"
  | "not_measurable";

export type TranscriptEntry = {
  period: string;
  filed_on: string;
  url: string;
  status: string;
  pages?: number;
  promises?: number;
  dropped_quotes?: number;
  dropped_figures?: number;
};

export type LedgerBody = {
  symbol: string;
  company: string;
  basis: string | null;
  quarters_on_file: string[];
  transcripts: TranscriptEntry[];
  counts: Partial<Record<LedgerStatus, number>>;
  built_on: string;
};

export type Promise_ = {
  id: string;
  metric: string;
  metric_key: string;
  thread_metric: string;
  kind: string;
  basis: string | null;
  scope: string | null;
  scope_note: string | null;
  value_low: number | null;
  value_high: number | null;
  unit: string | null;
  period_label: string | null;
  status: LedgerStatus;
  actual_note: string | null;
  quote: string;
  speaker: string | null;
  page: number | null;
  call_date: string;
  source_url: string | null;
};

export async function listLedgers() {
  return query<{ symbol: string; company: string; body: LedgerBody; built_at: string }>(
    `select distinct on (d.isin) a.value as symbol, c.name as company, d.body, d.built_at::text
       from dossier_sections d
       join companies c on c.isin = d.isin
       join company_aliases a on a.isin = d.isin and a.kind = 'nse_symbol' and a.valid_to is null
      where d.section = 'ledger'
      order by d.isin, d.built_at desc`,
  );
}

export async function getLedger(symbol: string) {
  const [head] = await query<{ isin: string; company: string; body: LedgerBody; built_at: string }>(
    `select d.isin, c.name as company, d.body, d.built_at::text
       from dossier_sections d
       join companies c on c.isin = d.isin
       join company_aliases a on a.isin = d.isin and a.kind = 'nse_symbol' and a.valid_to is null
      where a.value = upper($1) and d.section = 'ledger'
      order by d.built_at desc limit 1`,
    [symbol],
  );
  if (!head) return null;
  const promises = await query<Promise_>(
    `select g.id::text, g.metric, g.metric_key,
            coalesce(g.extraction ->> 'metric_key', g.metric_key) as thread_metric,
            g.kind, g.basis, g.scope, g.scope_note,
            g.value_low::float8 as value_low, g.value_high::float8 as value_high, g.unit,
            g.period_label, g.status, g.actual_note, g.quote, g.speaker, g.page,
            g.call_date::text as call_date, d.source_url
       from guidance g join documents d on d.id = g.document_id
      where g.isin = $1
      order by g.call_date desc, g.id`,
    [head.isin],
  );
  return { ...head, promises };
}

export async function hasLedger(isin: string): Promise<boolean> {
  const rows = await query("select 1 from dossier_sections where isin = $1 and section = 'ledger' limit 1", [isin]);
  return rows.length > 0;
}
