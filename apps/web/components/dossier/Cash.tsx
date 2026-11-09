import Cite from "./Cite";
import type { CashBody, CashNote, CashYear } from "@/lib/dossier";
import { fmtCrore, fmtShare } from "@/lib/format";

type Row = { key: keyof CashYear; label: string; computed?: boolean; pct?: boolean };

const ROWS: Row[] = [
  { key: "cfo", label: "Operating cash flow" },
  { key: "capex", label: "Capital expenditure" },
  { key: "fcf", label: "Free cash flow", computed: true },
  { key: "pat", label: "Profit for the year" },
  { key: "cash_conversion_pct", label: "Operating cash flow ÷ profit", computed: true, pct: true },
  { key: "dividends", label: "Dividends paid" },
  { key: "buyback", label: "Buybacks" },
  { key: "payout", label: "Returned to shareholders", computed: true },
];
const LENDER_ROWS: Row[] = [
  { key: "cfo", label: "Operating cash flow" },
  { key: "pat", label: "Profit for the year" },
  { key: "capex", label: "Capital expenditure" },
  { key: "dividends", label: "Dividends paid" },
];

const FAILURE: Record<string, string> = {
  cash_flows_do_not_add_up: "operating, investing and financing flows do not add up to the change in cash",
  cash_flow_totals_missing: "the cash-flow totals could not all be read",
  profit_does_not_reconcile: "profit before tax less tax does not equal profit for the year",
  differs_from_quarterly_filings: "the full-year figures differ from the sum of the quarterly filings",
};

const LINE: Record<string, string> = {
  revenue: "revenue from operations",
  pat: "profit for the year",
  cfo: "operating cash flow",
};

function note(n: CashNote | string): string {
  if (typeof n === "string") return n; // written before notes were structured
  if (n.kind === "restated") {
    return `${n.fiscal_year} ${LINE[n.line] ?? n.line} was ₹${fmtCrore(n.was)} crore in the ${n.fiscal_year} report; the ${n.in_report} report restates it as ₹${fmtCrore(n.now)} crore, which FINN uses.`;
  }
  return `${n.fiscal_year}: the tax line could not be read, so profit was checked against the four quarterly filings instead.`;
}

function cell(y: CashYear, r: Row): string {
  const v = y[r.key];
  if (typeof v !== "number") return "–";
  return r.pct ? fmtShare(v) : fmtCrore(v);
}

export default function Cash({ cash, urls }: { cash?: CashBody; urls: Record<string, string> }) {
  if (!cash || cash.years.length === 0) {
    return <p className="empty">FINN could not read the statements of cash flows in the annual reports on NSE.</p>;
  }
  const years = cash.years.slice().reverse();
  const rows = cash.lender ? LENDER_ROWS : ROWS;
  const failing = cash.years.filter((y) => y.failures.length > 0);
  const t = cash.totals;
  const span = cash.years_in_totals.length
    ? `${cash.years_in_totals.at(-1)}–${cash.years_in_totals[0].slice(2)}`
    : "";
  return (
    <>
      {cash.lender && (
        <p className="notice">
          A lender&apos;s operating cash flow includes the money it lends out, so it is negative while the loan book
          grows. FINN does not compute free cash flow or cash conversion for banks and NBFCs.
        </p>
      )}
      {!cash.lender && t.cash_conversion_pct != null && (
        <section className="section" aria-label="Three years">
          <p className="lede">
            Over {span}, operating cash flow was <strong>{fmtShare(t.cash_conversion_pct)}</strong> of profit
            {t.fcf != null && (
              <>
                , and free cash flow came to <strong>₹{fmtCrore(t.fcf)} crore</strong>
              </>
            )}
            {t.payout_of_fcf_pct != null && (
              <>
                , of which dividends and buybacks took <strong>{fmtShare(t.payout_of_fcf_pct)}</strong>
              </>
            )}
            .
          </p>
        </section>
      )}

      <section className="section" aria-labelledby="flows">
        <h2 className="section-title" id="flows">
          Cash flows <span className="n">₹ crore, {cash.basis ?? "as filed"}</span>
        </h2>
        <div className="ctable-wrap">
          <table className="ctable">
            <thead>
              <tr>
                <th scope="col">
                  <span className="visually-hidden">Line</span>
                </th>
                {years.map((y) => (
                  <th scope="col" key={y.fiscal_year}>
                    {y.fiscal_year}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key} className={r.computed ? "computed" : undefined}>
                  <th scope="row">
                    {r.label}
                    {r.computed && <span className="visually-hidden"> (computed by FINN)</span>}
                  </th>
                  {years.map((y) =>
                    y.failures.length ? (
                      <td key={y.fiscal_year} className="na">
                        –
                      </td>
                    ) : (
                      <td key={y.fiscal_year}>{cell(y, r)}</td>
                    ),
                  )}
                </tr>
              ))}
              <tr>
                <th scope="row">Statement page</th>
                {years.map((y) => (
                  <td key={y.fiscal_year}>
                    <Cite doc={y.document_id} page={y.pages.cfo ?? y.pages.net_change} />
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
        {failing.map((y) => (
          <p className="notice" key={y.fiscal_year}>
            <strong>{y.fiscal_year}: numbers need a look.</strong> {y.failures.map((f) => FAILURE[f] ?? f).join("; ")}, so
            FINN shows none of this year&apos;s figures.{" "}
            {y.document_id && urls[String(y.document_id)] && (
              <a href={`${urls[String(y.document_id)]}#page=${y.pages.cfo ?? y.pages.revenue ?? 1}`} target="_blank" rel="noopener noreferrer">
                Open the filing
              </a>
            )}
          </p>
        ))}
        {cash.years.some((y) => y.withheld.length > 0) && (
          <p className="section-note">
            A dash where FINN found a line on the statement that it could not read with certainty, so it did not add
            up a total that might be short.
          </p>
        )}
        <p className="section-note" style={{ marginTop: "0.6rem" }}>
          Figures from the statements of cash flows and of profit and loss in the last two annual reports; the page
          link opens the statement with its figures. Shaded rows are computed by FINN: free cash flow is operating cash flow less
          capital expenditure; returned to shareholders is dividends plus buybacks. Each year&apos;s operating,
          investing and financing flows are checked to add up to its change in cash before anything is shown.
        </p>
        {cash.notes.length > 0 && (
          <ul className="section-note">
            {cash.notes.map((n) => (
              <li key={typeof n === "string" ? n : `${n.kind}${n.fiscal_year}${"line" in n ? n.line : ""}`}>{note(n)}</li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
