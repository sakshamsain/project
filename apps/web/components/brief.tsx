import Link from "next/link";
import PeopleCard from "@/components/PeopleCard";
import ResultsCard from "@/components/ResultsCard";
import { fmtDay, fmtMultiple, fmtPct, fmtScore, fmtWhen } from "@/lib/format";
import { categoryLabel } from "@/lib/labels";
import type { Breakdown, BriefRow, Reaction } from "@/lib/queries";

const FRONT_THRESHOLD = 0.75; // finn.push.score.FRONT_THRESHOLD, mirrored in brief()

export function Ticker({ symbol, quiet = false }: { symbol: string | null; quiet?: boolean }) {
  if (!symbol) return null;
  return (
    <Link className={quiet ? "stamp quiet" : "stamp"} href={`/company/${encodeURIComponent(symbol)}`}>
      {symbol}
    </Link>
  );
}

export function ReactionLine({ r }: { r: Reaction }) {
  if (r.return_pct == null) return null;
  const dir = r.return_pct < 0 ? "down" : "up";
  const glyph = r.return_pct < 0 ? "▼" : "▲";
  const parts: string[] = [];
  if (r.abnormal_return_pct != null && r.index_return_pct != null) {
    parts.push(`${fmtPct(r.abnormal_return_pct)} against the Nifty`);
  }
  if (r.volume_multiple != null) parts.push(`volume ${fmtMultiple(r.volume_multiple)} its 20-day average`);
  return (
    <p className="reaction">
      <span className={dir}>
        {glyph} {fmtPct(r.return_pct)}
      </span>{" "}
      on {fmtDay(r.trade_date)}
      {parts.length > 0 && <>, {parts.join(", ")}</>}
    </p>
  );
}

export function Why({ b, category, stage }: { b: Breakdown | null; category: string; stage: string | null }) {
  if (!b) return null;
  const c = b.contributions;
  return (
    <details className="why">
      <summary>Why it is here</summary>
      {c ? (
        <table>
          <tbody>
            <tr>
              <td>{categoryLabel(category, stage)}, weight of the category</td>
              <td>{fmtScore(c.category)}</td>
            </tr>
            {c.size > 0 && (
              <tr>
                <td>Size against market value</td>
                <td>+{fmtScore(c.size)}</td>
              </tr>
            )}
            {c.reaction > 0 && (
              <tr>
                <td>Price or volume reaction</td>
                <td>+{fmtScore(c.reaction)}</td>
              </tr>
            )}
            <tr>
              <td>
                {b.is_restatement
                  ? "Revision of an earlier filing"
                  : b.is_first_filing
                    ? "First of its kind in 30 days"
                    : "Similar filing in the last 30 days"}
              </td>
              <td>+{fmtScore(c.novelty)}</td>
            </tr>
            {b.floor_applied && (
              <tr>
                <td>Always shown: top-management or auditor exit, downgrade, or pledge increase</td>
                <td>min {fmtScore(FRONT_THRESHOLD)}</td>
              </tr>
            )}
            <tr className="total">
              <td>Score (front page from {fmtScore(FRONT_THRESHOLD)})</td>
              <td>{fmtScore(b.score)}</td>
            </tr>
          </tbody>
        </table>
      ) : (
        <p className="section-note">Score {fmtScore(b.score)}.</p>
      )}
    </details>
  );
}

export function Story({ r }: { r: BriefRow }) {
  const reaction = r.enrichment?.reaction;
  return (
    <article className="story">
      <div className="story-meta">
        <Ticker symbol={r.symbol} />
        <span>{categoryLabel(r.category, r.stage)}</span>
        <time dateTime={r.first_seen_at}>{fmtWhen(r.first_seen_at)}</time>
      </div>
      <h3>
        <Link href={`/event/${r.event_id}`}>{r.headline ?? "Exchange filing"}</Link>
      </h3>
      {r.why_it_matters && <p className="section-note">{r.why_it_matters}</p>}
      {r.enrichment?.results_card && (
        <ResultsCard card={r.enrichment.results_card} filingUrl={r.attachment_url} />
      )}
      {r.enrichment?.ledger?.measured && r.symbol && (
        <p className="ledger-line">
          <Link href={`/event/${r.event_id}`}>Promise Ledger</Link>:{" "}
          {(["delivered", "on_track", "off_track", "missed"] as const)
            .filter((k) => r.enrichment?.ledger?.counts[k])
            .map((k) => `${r.enrichment?.ledger?.counts[k]} ${k.replace("_", " ")}`)
            .join(", ") || "nothing measurable yet"}
        </p>
      )}
      {r.enrichment?.people_card && <PeopleCard card={r.enrichment.people_card} compact />}
      {reaction && <ReactionLine r={reaction} />}
      <div className="story-foot">
        {r.filing_count > 1 && <span>{r.filing_count} filings</span>}
        {r.attachment_url && (
          <a href={r.attachment_url} target="_blank" rel="noopener noreferrer">
            Open the filing
          </a>
        )}
      </div>
      <Why b={r.score_breakdown} category={r.category} stage={r.stage} />
    </article>
  );
}

export function Line({ r }: { r: BriefRow }) {
  return (
    <li className="line">
      <Ticker symbol={r.symbol} quiet />
      <div className="line-text">
        <Link href={`/event/${r.event_id}`}>{r.headline ?? "Exchange filing"}</Link>
        <span className="line-kind">
          {categoryLabel(r.category, r.stage)}
          {r.filing_count > 1 ? `, ${r.filing_count} filings` : ""},{" "}
          <time dateTime={r.first_seen_at}>{fmtWhen(r.first_seen_at)}</time>
        </span>
      </div>
    </li>
  );
}

export function Routine({ rows }: { rows: BriefRow[] }) {
  if (rows.length === 0) return null;
  const groups = new Map<string, BriefRow[]>();
  for (const r of rows) {
    const k = categoryLabel(r.category, r.stage);
    groups.set(k, [...(groups.get(k) ?? []), r]);
  }
  const ordered = [...groups.entries()].sort((a, b) => b[1].length - a[1].length);
  const filings = rows.reduce((n, r) => n + r.filing_count, 0);
  return (
    <details className="routine">
      <summary>
        <span>Routine</span>
        <span className="hint">
          {filings} {filings === 1 ? "filing" : "filings"}, folded
        </span>
      </summary>
      <div className="routine-body">
        {ordered.map(([label, items]) => (
          <div className="routine-group" key={label}>
            <h4>
              {label} ({items.length})
            </h4>
            <ul className="lines">
              {items.map((r) => (
                <Line key={r.event_id} r={r} />
              ))}
            </ul>
          </div>
        ))}
      </div>
    </details>
  );
}
