import { fmtDay } from "@/lib/format";
import type { LedgerStatus, Promise_ } from "@/lib/research";

export const STATUS: Record<LedgerStatus, string> = {
  delivered: "Delivered",
  missed: "Missed",
  on_track: "On track",
  off_track: "Off track",
  too_early: "Too early",
  not_measurable: "Not in the filings",
};

const ORDER: LedgerStatus[] = ["missed", "off_track", "on_track", "delivered", "too_early", "not_measurable"];

const METRIC: Record<string, string> = {
  revenue: "Revenue",
  revenue_growth: "Revenue growth",
  ebitda: "EBITDA",
  ebitda_growth: "EBITDA growth",
  ebitda_margin: "EBITDA margin",
  ebit_margin: "Operating (EBIT) margin",
  pat: "Net profit",
  pat_growth: "Net profit growth",
  pat_margin: "Net profit margin",
  capex: "Capital expenditure",
  capacity: "Capacity",
  order_inflow: "Order inflow",
  order_book: "Order book",
  volume: "Volumes",
  aum_growth: "AUM growth",
  loan_growth: "Loan growth",
  credit_cost: "Credit cost",
  net_interest_margin: "Net interest margin",
  deal_wins: "Deal wins",
  headcount: "Hiring",
};

function title(p: Promise_): string {
  const key = p.metric_key !== "other" ? p.metric_key : p.thread_metric;
  const m = key !== "other" ? (METRIC[key] ?? p.metric) : p.metric;
  const what = p.scope === "segment" && p.scope_note ? `${m}, ${p.scope_note}` : m;
  return what.charAt(0).toUpperCase() + what.slice(1);
}

// One thread per thing promised: the model's own metric (before code narrowed it for
// checking), its basis, scope and period. A thread shows how the promise moved call to call.
function threadKey(p: Promise_): string {
  const m = p.thread_metric !== "other" ? p.thread_metric : p.metric.toLowerCase();
  const scope = p.scope === "segment" ? (p.scope_note ?? "").toLowerCase() : p.scope;
  return [m, p.basis, scope, p.period_label ?? ""].join("|");
}

/** How a promise compares with the one made on the previous call in its thread. */
export function revision(now: Promise_, before: Promise_ | undefined): string | null {
  if (!before) return null;
  const a = [now.value_low, now.value_high];
  const b = [before.value_low, before.value_high];
  if (a.some((x) => x == null) || b.some((x) => x == null)) return null;
  const [nl, nh] = a as number[];
  const [bl, bh] = b as number[];
  if (nl === bl && nh === bh) return "kept";
  if (nl >= bl && nh >= bh) return "raised";
  if (nl <= bl && nh <= bh) return "cut";
  return "changed";
}

function target(p: Promise_): string | null {
  const unit = p.unit === "%" ? "%" : p.unit === "bps" ? " bps" : p.unit === "crore" ? " Cr" : "";
  const pre = p.unit === "crore" ? "₹" : "";
  const f = (x: number) => `${pre}${x.toLocaleString("en-IN", { maximumFractionDigits: 2 })}${unit}`;
  const lo = p.value_low;
  const hi = p.value_high;
  if (lo != null && hi != null) return lo === hi ? f(lo) : `${f(lo)} to ${f(hi)}`;
  if (lo != null) return `at least ${f(lo)}`;
  if (hi != null) return `at most ${f(hi)}`;
  return null;
}

const BASIS: Record<string, string> = { constant_currency: "constant currency", usd: "US dollars" };

type Thread = { key: string; items: Promise_[] };

export function threads(promises: Promise_[]): Thread[] {
  const map = new Map<string, Promise_[]>();
  for (const p of promises) map.set(threadKey(p), [...(map.get(threadKey(p)) ?? []), p]);
  const out = [...map.entries()].map(([key, items]) => ({
    key,
    items: items.sort((a, b) => b.call_date.localeCompare(a.call_date)),
  }));
  return out.sort(
    (a, b) =>
      ORDER.indexOf(a.items[0].status) - ORDER.indexOf(b.items[0].status) ||
      b.items.length - a.items.length ||
      b.items[0].call_date.localeCompare(a.items[0].call_date),
  );
}

export function ThreadCard({ t }: { t: Thread }) {
  const latest = t.items[0];
  const tgt = target(latest);
  return (
    <article className="thread">
      <header className="thread-head">
        <h3>
          {title(latest)}
          {latest.period_label && latest.period_label !== "unspecified" ? (
            <span className="thread-period">{latest.period_label}</span>
          ) : (
            <span className="thread-period">no date given</span>
          )}
        </h3>
        <span className={`chip ${latest.status}`}>{STATUS[latest.status]}</span>
      </header>
      <p className="thread-check">
        {latest.status === "not_measurable" || !latest.actual_note ? (
          <>
            {tgt && (
              <>
                Promised {tgt}
                {latest.basis && BASIS[latest.basis] ? ` in ${BASIS[latest.basis]}` : ""}.{" "}
              </>
            )}
            {latest.actual_note}
          </>
        ) : (
          latest.actual_note
        )}
      </p>
      <ol className="said">
        {t.items.map((p, i) => {
          const rev = revision(p, t.items[i + 1]);
          const said = target(p);
          return (
          <li key={p.id}>
            <span className="said-when">
              {fmtDay(p.call_date)} call{p.speaker ? `, ${p.speaker}` : ""}
              {said ? `: ${said}` : ""}
              {rev ? <span className={`rev ${rev}`}> {rev}</span> : null}
            </span>
            <q>{p.quote}</q>{" "}
            {p.source_url && p.page ? (
              <a className="cite" href={`${p.source_url}#page=${p.page}`} target="_blank" rel="noopener noreferrer">
                p.&nbsp;{p.page}
              </a>
            ) : null}
          </li>
          );
        })}
      </ol>
    </article>
  );
}
