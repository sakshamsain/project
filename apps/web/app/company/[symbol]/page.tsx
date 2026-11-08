import Link from "next/link";
import { notFound } from "next/navigation";
import { fmtDay, fmtPct, fmtPrice, fmtWhen } from "@/lib/format";
import { categoryLabel } from "@/lib/labels";
import { currentProfile } from "@/lib/profile";
import { getCompany } from "@/lib/queries";
import { hasLedger } from "@/lib/research";
import { addHolding, removeHolding } from "../../settings/actions";

export const dynamic = "force-dynamic";

function Spark({ closes }: { closes: number[] }) {
  if (closes.length < 2) return null;
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const span = max - min || 1;
  const pts = closes
    .map((c, i) => `${((i / (closes.length - 1)) * 100).toFixed(2)},${(36 - ((c - min) / span) * 32).toFixed(2)}`)
    .join(" ");
  return (
    <svg className="spark" viewBox="0 0 100 40" preserveAspectRatio="none" role="img" aria-label={`Closing prices, last ${closes.length} sessions`}>
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.4" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

const TIER: Record<string, string> = { front: "Read first", oneliner: "In brief", folded: "Routine" };

export default async function CompanyPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  const profile = await currentProfile();
  const data = await getCompany(decodeURIComponent(symbol), profile.id);
  if (!data) notFound();
  const { company: c, bars, events, meetings, held } = data;
  const ledger = await hasLedger(c.isin);
  const last = bars.at(-1);
  const ret = last?.prev_close ? (last.close / last.prev_close - 1) * 100 : null;
  return (
    <main className="page">
      <header className="masthead">
        <Link className="wordmark" href="/">
          FINN
        </Link>
        <span className="dateline">{c.industry ?? ""}</span>
      </header>

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
        <Spark closes={bars.map((b) => b.close)} />
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
          Last 60 days <span className="n">{events.length}</span>
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
