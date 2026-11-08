import Link from "next/link";
import { notFound } from "next/navigation";
import { ReactionLine, Ticker, Why } from "@/components/brief";
import ResultsCard from "@/components/ResultsCard";
import { fmtDay, fmtMultiple, fmtPct, fmtWhen } from "@/lib/format";
import { ANOMALY, categoryLabel } from "@/lib/labels";
import { getEvent } from "@/lib/queries";
import { clean } from "@/lib/text";

export const dynamic = "force-dynamic";

const TIER: Record<string, string> = { front: "Read first", oneliner: "In brief", folded: "Routine" };

export default async function EventPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await getEvent(id);
  if (!data) notFound();
  const { event: e, filings, hits } = data;
  const reaction = e.enrichment?.reaction;
  return (
    <main className="page">
      <header className="masthead">
        <Link className="wordmark" href="/">
          FINN
        </Link>
        <span className="dateline">{TIER[e.tier] ?? ""}</span>
      </header>

      <article className="section" style={{ marginTop: "1.25rem" }}>
        <div className="story-meta">
          <Ticker symbol={e.symbol} />
          <span>{e.company}</span>
        </div>
        <h1 className="triage-line" style={{ fontSize: "clamp(1.6rem, 6vw, 2.2rem)", margin: "0.6rem 0 0.4rem" }}>
          {e.headline ?? "Exchange filing"}
        </h1>
        <p className="section-note" style={{ margin: "0 0 0.5rem" }}>
          {categoryLabel(e.category, e.stage)}, first filed {fmtWhen(e.first_seen_at)} IST
        </p>
        {e.enrichment?.results_card && (
          <ResultsCard card={e.enrichment.results_card} filingUrl={filings[0]?.attachment_url} />
        )}
        {reaction && <ReactionLine r={reaction} />}
        <Why b={e.score_breakdown} category={e.category} stage={e.stage} />
      </article>

      {hits.length > 0 && (
        <section className="section" aria-labelledby="moves">
          <h2 className="section-title" id="moves">
            Market moves tied to it
          </h2>
          <ul className="lines">
            {hits.map((h) => (
              <li className="line" key={`${h.kind}-${h.trade_date}`} style={{ gridTemplateColumns: "1fr auto" }}>
                <span>
                  {ANOMALY[h.kind] ?? h.kind}:{" "}
                  {h.kind === "volume_multiple"
                    ? `${fmtMultiple(h.value)} the 20-day average`
                    : h.kind === "delivery_spike"
                      ? `${h.value.toFixed(1)}% of traded shares taken for delivery`
                      : h.kind === "sigma_move"
                        ? `${fmtPct(h.value)}, ${Math.abs(h.zscore ?? 0).toFixed(1)} standard deviations`
                        : fmtPct(h.value)}
                </span>
                <span className="when">{fmtDay(h.trade_date)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="section" aria-labelledby="filings">
        <h2 className="section-title" id="filings">
          {filings.length === 1 ? "The filing" : `${filings.length} filings`}
        </h2>
        <ul className="lines">
          {filings.map((f) => (
            <li className="line" key={f.filed_at + f.subject} style={{ gridTemplateColumns: "1fr auto" }}>
              <div className="line-text">
                {f.attachment_url ? (
                  <a href={f.attachment_url} target="_blank" rel="noopener noreferrer">
                    {clean(f.body_text) || f.subject}
                  </a>
                ) : (
                  clean(f.body_text) || f.subject
                )}
                <span className="line-kind">
                  {f.subject}
                  {f.classified_by === "rules" && f.rule_id ? `, matched rule ${f.rule_id}` : ""}
                </span>
                {f.summary && (
                  <details className="nse-summary">
                    <summary>NSE&apos;s summary</summary>
                    <p>{f.summary}</p>
                  </details>
                )}
              </div>
              <time dateTime={f.filed_at}>{fmtWhen(f.filed_at)}</time>
            </li>
          ))}
        </ul>
        <p className="section-note" style={{ marginTop: "0.75rem" }}>
          Each filing links to its PDF on NSE. Summaries are written by NSE, not by FINN.
        </p>
      </section>
    </main>
  );
}
