// The Dossier as the worker stored it: one dossier_sections row per part. Every figure
// here was extracted and checked, or computed, by the worker; the web only lays it out.
import { query } from "./db";

export type Cited = { title: string; quote: string; page: number };

export type CashYear = {
  fiscal_year: string;
  revenue: number | null;
  pat: number | null;
  cfo: number | null;
  capex: number | null;
  fcf: number | null;
  cash_conversion_pct: number | null;
  dividends: number | null;
  buyback: number | null;
  payout: number | null;
  revenue_growth_pct: number | null;
  pat_growth_pct: number | null;
  pages: Record<string, number>;
  document_id: number | null;
  failures: string[];
  withheld: string[];
  /** Year-end balance-sheet figures and ratios, computed by the worker; absent in older dossiers. */
  balance?: Partial<Record<BalanceKey, number | null>>;
  balance_failures?: string[];
  quarters: { status?: string; revenue?: { annual: number; quarters: number }; pat?: { annual: number; quarters: number } };
};

export type BalanceKey =
  | "equity"
  | "total_assets"
  | "borrowings"
  | "cash_and_bank"
  | "net_debt"
  | "debt_to_equity"
  | "receivable_days"
  | "inventory_days"
  | "payable_days"
  | "cash_cycle_days"
  | "interest_cover"
  | "roce_pct";

export type CashBody = {
  lender: boolean;
  basis: string | null;
  years: CashYear[];
  totals: { cfo?: number; pat?: number; cash_conversion_pct?: number; fcf?: number; payout?: number; payout_of_fcf_pct?: number | null };
  years_in_totals: string[];
  notes: CashNote[];
};

export type CashNote =
  | { kind: "restated"; fiscal_year: string; line: string; was: number; now: number; in_report: string }
  | { kind: "profit_checked_by_quarters"; fiscal_year: string };

export type Share = { name: string; share: number | null; nic: string | null; page: number };

export type BusinessBody = {
  description: Cited | null;
  activities: Share[];
  products: Share[];
  boundary: string | null;
  states: { value: number; page: number } | null;
  countries: { value: number; page: number } | null;
  exports: { value: number; page: number } | null;
  fiscal_year: string;
  document_id: number | null;
  error?: string;
};

export type AuditorBody = {
  kind: "unmodified" | "qualified" | "adverse" | "disclaimer" | null;
  page: number | null;
  firm: string | null;
  matters: Cited[];
  emphasis: Cited[];
  drawn_attention: { kind: string; quote: string; page: number }[];
  fiscal_year: string;
  document_id: number | null;
  error?: string;
};

export type RisksBody = { risks: Cited[]; fiscal_year: string; document_id: number | null; error?: string };

export type Fact = {
  id: string;
  text: string;
  kind: "computed" | "promise" | "quote";
  document_id: number | null;
  page: number | null;
  quote: string | null;
};

export type CaseBody = {
  bull: { text: string; facts: string[] }[];
  bear: { text: string; facts: string[] }[];
  facts: Fact[];
  dropped: string[];
  model: string | null;
  error?: string;
};

export type ReportEntry = {
  fiscal_year: string;
  url: string;
  filed_on: string | null;
  revised: boolean;
  status: string;
  pages: number;
  document_id: number | null;
  basis: string | null;
  sections: Record<string, number[]>;
};

export type SourcesBody = { reports: ReportEntry[]; built_on: string };

export type Sections = {
  annual_reports?: SourcesBody;
  cash?: CashBody;
  business?: BusinessBody;
  auditor?: AuditorBody;
  risks?: RisksBody;
  case?: CaseBody;
};

export async function getSections(isin: string): Promise<{ sections: Sections; built_at: string | null }> {
  const rows = await query<{ section: string; body: unknown; built_at: string }>(
    `select distinct on (section) section, body, built_at::text
       from dossier_sections
      where isin = $1 and section <> 'ledger'
      order by section, built_at desc`,
    [isin],
  );
  const sections: Record<string, unknown> = {};
  let built: string | null = null;
  for (const r of rows) {
    sections[r.section] = r.body;
    if (!built || r.built_at > built) built = r.built_at;
  }
  return { sections: sections as Sections, built_at: built };
}

export type QuarterRow = { period: string; metric: string; value: number; basis: string };

export async function getQuarters(isin: string): Promise<QuarterRow[]> {
  return query<QuarterRow>(
    `with b as (
       select case when bool_or(basis = 'consolidated') then 'consolidated' else 'standalone' end as basis
         from financials where isin = $1 and period_type = 'Q'
     )
     select f.period, f.metric, f.value_cr::float8 as value, f.basis
       from financials f, b
      where f.isin = $1 and f.period_type = 'Q' and f.basis = b.basis
        and f.metric in ('revenue', 'nii', 'pat')`,
    [isin],
  );
}

export async function getPriceHead(isin: string) {
  const [p] = await query<{ trade_date: string; close: number; prev_close: number | null }>(
    `select trade_date::text, close::float8 as close, prev_close::float8 as prev_close
       from eod_prices where isin = $1 order by trade_date desc limit 1`,
    [isin],
  );
  return p ?? null;
}

export type SourcePage = {
  id: string;
  title: string | null;
  doc_type: string;
  period: string | null;
  source_url: string | null;
  pages: number | null;
  page_no: number;
  text: string | null;
  symbol: string | null;
  company: string;
};

export async function getSourcePage(doc: string, page: number): Promise<SourcePage | null> {
  const [row] = await query<SourcePage>(
    `select d.id::text, d.title, d.doc_type, d.period, d.source_url, d.pages, $2::int as page_no,
            p.text, c.name as company,
            (select a.value from company_aliases a
              where a.isin = d.isin and a.kind = 'nse_symbol' and a.valid_to is null limit 1) as symbol
       from documents d
       join companies c on c.isin = d.isin
       left join doc_pages p on p.document_id = d.id and p.page_no = $2
      where d.id = $1`,
    [doc, page],
  );
  return row ?? null;
}
