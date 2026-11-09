import Cite from "./Cite";
import QuarterChart from "@/components/charts/QuarterChart";
import type { CashBody, QuarterRow } from "@/lib/dossier";
import { fmtCrore, fmtPct } from "@/lib/format";
import { series } from "@/lib/quarters";

export default function Trajectory({ quarters, cash }: { quarters: QuarterRow[]; cash?: CashBody }) {
  const lender = quarters.some((q) => q.metric === "nii");
  const top = series(quarters, lender ? "nii" : "revenue");
  const pat = series(quarters, "pat");
  const years = (cash?.years ?? []).slice().reverse(); // oldest first
  return (
    <>
      {years.length > 0 && (
        <section className="section" aria-labelledby="years">
          <h2 className="section-title" id="years">
            By year <span className="n">₹ crore, {cash?.basis ?? "as filed"}</span>
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
                <tr>
                  <th scope="row">{cash?.lender ? "Total revenue from operations" : "Revenue from operations"}</th>
                  {years.map((y) => (
                    <td key={y.fiscal_year}>
                      {y.failures.length ? "check" : y.revenue != null ? fmtCrore(y.revenue) : "–"}
                      {!y.failures.length && y.revenue_growth_pct != null && (
                        <span className="cell-sub">{fmtPct(y.revenue_growth_pct)}</span>
                      )}
                    </td>
                  ))}
                </tr>
                <tr>
                  <th scope="row">Profit for the year</th>
                  {years.map((y) => (
                    <td key={y.fiscal_year}>
                      {y.failures.length ? "check" : y.pat != null ? fmtCrore(y.pat) : "–"}
                      {!y.failures.length && y.pat_growth_pct != null && <span className="cell-sub">{fmtPct(y.pat_growth_pct)}</span>}
                    </td>
                  ))}
                </tr>
                <tr>
                  <th scope="row">Source</th>
                  {years.map((y) => (
                    <td key={y.fiscal_year}>
                      <Cite doc={y.document_id} page={y.pages.revenue ?? y.pages.pat} />
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
          <p className="section-note" style={{ marginTop: "0.6rem" }}>
            From the statements of profit and loss in the last two annual reports; change on the year before beneath
            each figure.{" "}
            {years.some((y) => y.quarters.status === "matches") &&
              `${years
                .filter((y) => y.quarters.status === "matches")
                .map((y) => y.fiscal_year)
                .join(" and ")} revenue and profit equal the sum of that year's four quarterly filings.`}
          </p>
        </section>
      )}

      {top.length > 1 ? (
        <section className="section" aria-labelledby="quarters">
          <h2 className="section-title" id="quarters">
            By quarter
          </h2>
          <div className="qcharts">
            <QuarterChart title={lender ? "Net interest income" : "Revenue"} points={top} />
            {pat.length > 1 && <QuarterChart title="Net profit" points={pat} />}
          </div>
          <p className="section-note">
            From the company&apos;s XBRL results filings on NSE, {quarters[0]?.basis ?? "consolidated"}. Tap a bar for
            its change on the quarter and the year.
          </p>
        </section>
      ) : (
        <p className="empty">No quarterly filings on file yet.</p>
      )}
    </>
  );
}
