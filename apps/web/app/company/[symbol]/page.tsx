import Link from "next/link";
import Masthead from "@/components/Masthead";
import { notFound } from "next/navigation";
import { fmtDay, fmtPct, fmtPrice, fmtWhen } from "@/lib/format";
import PriceChart from "@/components/charts/PriceChart";
import QuarterChart, { type QuarterPoint } from "@/components/charts/QuarterChart";
import { categoryLabel } from "@/lib/labels";
import { currentProfile } from "@/lib/profile";
import { getCompany } from "@/lib/queries";
import { hasLedger } from "@/lib/research";
import { addHolding, removeHolding } from "../../settings/actions";

export const dynamic = "force-dynamic";

function series(rows: { period: string; metric: string; value: number }[], metric: string): QuarterPoint[] {
  return rows
    .filter((r) => r.metric === metric)
    .map((r) => {
      const m = /^Q([1-4])FY(\d{2})$/.exec(r.period);
      return m ? { label: `Q${m[1]} FY${m[2]}`, q: Number(m[1]), fy: Number(m[2]), value: r.value } : null;
    })
    .filter((p): p is QuarterPoint => p !== null)
    .sort((a, b) => a.fy - b.fy || a.q - b.q)
    .slice(-8);
}

const TIER: Record<string, string> = { front: "Read first", oneliner: "In brief", folded: "Routine" };

export default async function CompanyPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  const profile = await currentProfile();
  const data = await getCompany(decodeURIComponent(symbol), profile.id);
  if (!data) notFound();
  const { company: c, bars, events, meetings, held, marks, quarters } = data;
  const lender = quarters.some((q) => q.metric === "nii");
  const top = series(quarters, lender ? "nii" : "revenue");
  const pat = series(quarters, "pat");
  const ledger = await hasLedger(c.isin);
  const last = bars.at(-1);
  const ret = last?.prev_close ? (last.close / last.prev_close - 1) * 100 : null;
  return (
    <main className="page">
      <Masthead user={profile.user} note={c.industry ?? ""} />

      <section className="triage" aria-label="Company">
        <span className="stamp">{c.symbol}</span>
        <h1 className="triage-line" style={{ fontSize: "clamp(1.8rem, 7vw, 2.5rem)", marginTop: "0.5rem" }}>
          {c.name}
        </h1>
        {last && (
          <p className="triage-sub">
            {fmtPrice(last.close)} at the close on {fmtDay(last.trade_date)}
            {ret != null && (
              <>
                , <span className={ret < 0 ? "down" : "up"}>{ret < 0 ? "▼" : "▲"} {fmtPct(ret)}</span>
              </>
            )}
          </p>
        )}
        {bars.length > 1 && (
          <PriceChart
            symbol={c.symbol}
            bars={bars.map((b) => ({ d: b.trade_date, close: b.close, volume: b.volume }))}
            events={marks.map((m) => ({
              d: m.d,
              id: m.id,
              headline: m.headline ?? "Exchange filing",
              tier: m.tier,
              label: categoryLabel(m.category, m.stage),
            }))}
          />
        )}
        <form action={held ? removeHolding : addHolding} style={{ marginTop: "0.75rem" }}>
          <input type="hidden" name="isin" value={c.isin} />
          <input type="hidden" name="symbol" value={c.symbol} />
          <input type="hidden" name="back" value={`/company/${c.symbol}`} />
          <button className={held ? "button ghost small" : "button small"} type="submit">
            {held ? "Remove from portfolio" : "Add to portfolio"}
          </button>
          {ledger && (
            <Link className="button ghost small" href={`/research/${c.symbol}`} style={{ marginLeft: "0.5rem", textDecoration: "none" }}>
              Promise ledger
            </Link>
          )}
        </form>
      </section>

      {top.length > 1 && (
        <section className="section" aria-labelledby="quarters">
          <h2 className="section-title" id="quarters">
            Quarterly results
          </h2>
          <div className="qcharts">
            <QuarterChart title={lender ? "Net interest income" : "Revenue"} points={top} />
            {pat.length > 1 && <QuarterChart title="Net profit" points={pat} />}
          </div>
          <p className="section-note">
            From the company&apos;s XBRL filings on NSE, {quarters[0]?.basis ?? "consolidated"}. Tap a bar for
            its change on the quarter and the year.
          </p>
        </section>
      )}

      {meetings.length > 0 && (
        <section className="section" aria-labelledby="meetings">
          <h2 className="section-title" id="meetings">
            Board meetings
          </h2>
          <ul className="lines">
            {meetings.map((m) => (
              <li className="line" key={m.meeting_date} style={{ gridTemplateColumns: "auto 1fr" }}>
                <span className="when">{fmtDay(m.meeting_date)}</span>
                <span className="line-text">{m.is_results ? "Results" : (m.description ?? "Board meeting")}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="section" aria-labelledby="events">
        <h2 className="section-title" id="events">
          Filings, last 60 days <span className="n">{events.length}</span>
        </h2>
        {events.length === 0 ? (
          <p className="empty">No filings in the last 60 days.</p>
        ) : (
          <ul className="lines">
            {events.map((e) => (
              <li className="line" key={e.event_id} style={{ gridTemplateColumns: "1fr auto" }}>
                <div className="line-text">
                  <Link href={`/event/${e.event_id}`}>{e.headline ?? "Exchange filing"}</Link>
                  <span className="line-kind">
                    {categoryLabel(e.category, e.stage)}, {TIER[e.tier] ?? e.tier}
                    {e.filing_count > 1 ? `, ${e.filing_count} filings` : ""}
                  </span>
                </div>
                <time dateTime={e.first_seen_at}>{fmtWhen(e.first_seen_at)}</time>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
