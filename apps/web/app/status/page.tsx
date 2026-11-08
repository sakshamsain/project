import Link from "next/link";
import { fmtWhen } from "@/lib/format";
import { getStatus } from "@/lib/queries";

export const dynamic = "force-dynamic";
export const metadata = { title: "Data sources" };

const SOURCE: Record<string, string> = {
  nse_announcements: "NSE corporate announcements",
  nse_delivery_file: "NSE daily bars with delivery",
  nse_index_closes: "NSE index closes",
  nse_corporate_actions: "NSE corporate actions",
  nse_board_meetings: "NSE board meetings",
  nse_equity_master: "NSE list of equities",
  eod_done: "End-of-day run",
};

export default async function Status() {
  const { sources, counts } = await getStatus();
  return (
    <main className="page">
      <header className="masthead">
        <Link className="wordmark" href="/">
          FINN
        </Link>
        <span className="dateline">Data sources</span>
      </header>
      <section className="section" style={{ marginTop: "1.5rem" }}>
        <h2 className="section-title">Freshness</h2>
        <ul className="lines">
          {sources.map((s) => (
            <li className="line" key={s.source} style={{ gridTemplateColumns: "1fr auto" }}>
              <div className="line-text">
                {SOURCE[s.source] ?? s.source}
                <span className="line-kind">
                  {s.consecutive_failures > 0
                    ? `Failing ${s.consecutive_failures} times in a row: ${s.last_error ?? "unknown error"}`
                    : "Working"}
                </span>
              </div>
              <span className="when">{s.last_ok_at ? fmtWhen(s.last_ok_at) : "never"}</span>
            </li>
          ))}
        </ul>
      </section>
      <section className="section">
        <h2 className="section-title">What FINN holds</h2>
        <dl className="kv">
          <dt>Listed companies</dt>
          <dd>{counts.companies.toLocaleString("en-IN")}</dd>
          <dt>Filings read</dt>
          <dd>{counts.filings.toLocaleString("en-IN")}</dd>
          <dt>Events after clustering</dt>
          <dd>{counts.events.toLocaleString("en-IN")}</dd>
          <dt>Unusual moves found</dt>
          <dd>{counts.anomalies.toLocaleString("en-IN")}</dd>
          <dt>Filings from</dt>
          <dd>{counts.first_filing ? fmtWhen(counts.first_filing) : "none"}</dd>
          <dt>Latest filing</dt>
          <dd>{counts.last_filing ? fmtWhen(counts.last_filing) : "none"}</dd>
          <dt>Latest prices</dt>
          <dd>{counts.last_bar ?? "none"}</dd>
          <dt>Model calls</dt>
          <dd>{counts.llm_calls}</dd>
          <dt>Model cost at list prices</dt>
          <dd>${counts.llm_cost.toFixed(2)}</dd>
        </dl>
      </section>
    </main>
  );
}
