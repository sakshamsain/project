import Link from "next/link";
import { notFound } from "next/navigation";
import { STATUS, ThreadCard, threads } from "@/components/Ledger";
import { fmtDay } from "@/lib/format";
import { getLedger, type LedgerStatus } from "@/lib/research";

export const dynamic = "force-dynamic";

const MEASURED: LedgerStatus[] = ["delivered", "missed", "on_track", "off_track", "too_early"];

export default async function LedgerPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  const data = await getLedger(decodeURIComponent(symbol));
  if (!data) notFound();
  const { body, promises, company } = data;
  const all = threads(promises);
  const checked = all.filter((t) => MEASURED.includes(t.items[0].status));
  const unchecked = all.filter((t) => !MEASURED.includes(t.items[0].status));
  const read = body.transcripts.filter((t) => t.status === "read");
  return (
    <main className="page">
      <header className="masthead">
        <Link className="wordmark" href="/research">
          FINN
        </Link>
        <span className="dateline">Promise ledger</span>
      </header>

      <section className="triage" aria-label="Summary">
        <Link className="stamp" href={`/company/${encodeURIComponent(body.symbol)}`}>
          {body.symbol}
        </Link>
        <h1 className="triage-line" style={{ fontSize: "clamp(1.8rem, 7vw, 2.5rem)", marginTop: "0.5rem" }}>
          {company}
        </h1>
        <p className="triage-sub">
          {promises.length} promises from {read.length} earnings calls. {checked.length} can be checked against the figures the company filed
          ({body.quarters_on_file.length} quarters, {body.basis?.toLowerCase() ?? "as filed"});
          the rest are about things the filings do not report.
        </p>
      </section>

      {checked.length > 0 && (
        <section className="section" aria-labelledby="checked">
          <h2 className="section-title" id="checked">
            Checked against the filings <span className="n">{checked.length}</span>
          </h2>
          <div className="threads">
            {checked.map((t) => (
              <ThreadCard key={t.key} t={t} />
            ))}
          </div>
        </section>
      )}

      {unchecked.length > 0 && (
        <section className="section" aria-labelledby="unchecked">
          <h2 className="section-title" id="unchecked">
            Promised, not in the filings <span className="n">{unchecked.length}</span>
          </h2>
          <p className="section-note">
            Each of these is quoted from a call; FINN cannot measure it from the quarterly
            statements, so it is tracked from call to call instead.
          </p>
          <div className="threads">
            {unchecked.map((t) => (
              <ThreadCard key={t.key} t={t} />
            ))}
          </div>
        </section>
      )}

      <section className="section" aria-labelledby="sources">
        <h2 className="section-title" id="sources">
          Sources
        </h2>
        <ul className="lines">
          {body.transcripts.map((t) => (
            <li className="line" key={t.url} style={{ gridTemplateColumns: "1fr" }}>
              <div className="line-text">
                <a href={t.url} target="_blank" rel="noopener noreferrer">
                  Earnings call on {fmtDay(t.filed_on)}, {t.period.replace(/(Q\d)(FY\d+)/, "$1 $2")} results
                </a>
                <span className="line-kind">
                  {t.status === "read"
                    ? `${t.pages} pages, ${t.promises} promises kept${t.dropped_quotes ? `, ${t.dropped_quotes} dropped because the quote was not in the text` : ""}`
                    : t.status}
                </span>
              </div>
            </li>
          ))}
        </ul>
        <p className="section-note" style={{ marginTop: "0.75rem" }}>
          Built {fmtDay(body.built_on)}. Statuses: {Object.entries(STATUS).map(([, v]) => v.toLowerCase()).join(", ")}.
        </p>
      </section>
    </main>
  );
}
