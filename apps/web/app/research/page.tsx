import Link from "next/link";
import { STATUS } from "@/components/Ledger";
import { listLedgers, type LedgerStatus } from "@/lib/research";

export const dynamic = "force-dynamic";
export const metadata = { title: "Research" };

const SHOWN: LedgerStatus[] = ["delivered", "on_track", "off_track", "missed", "not_measurable"];

export default async function Research() {
  const ledgers = await listLedgers();
  return (
    <main className="page">
      <header className="masthead">
        <Link className="wordmark" href="/">
          FINN
        </Link>
        <span className="dateline">Research</span>
      </header>
      <section className="triage">
        <p className="triage-line" style={{ fontSize: "clamp(1.9rem, 8vw, 2.6rem)" }}>
          What management promised,
          <br />
          <span className="kept">and what it delivered</span>
        </p>
        <p className="triage-sub">
          FINN reads each company&apos;s last four earnings-call transcripts on NSE, quotes every
          promise with its page, and checks it against the quarterly figures the company filed.
          Nothing else goes in: no news, no broker notes.
        </p>
      </section>

      <section className="section" aria-labelledby="ledgers">
        <h2 className="section-title" id="ledgers">
          Promise ledgers <span className="n">{ledgers.length}</span>
        </h2>
        {ledgers.length === 0 ? (
          <p className="empty">No ledgers built yet.</p>
        ) : (
          <ul className="lines">
            {ledgers.map((l) => {
              const total = Object.values(l.body.counts ?? {}).reduce((a, b) => a + (b ?? 0), 0);
              const parts = SHOWN.filter((s) => l.body.counts?.[s]).map(
                (s) => `${l.body.counts[s]} ${STATUS[s].toLowerCase()}`,
              );
              return (
                <li className="line" key={l.symbol}>
                  <Link className="stamp" href={`/research/${encodeURIComponent(l.symbol)}`}>
                    {l.symbol}
                  </Link>
                  <div className="line-text">
                    <Link href={`/research/${encodeURIComponent(l.symbol)}`}>{l.company}</Link>
                    <span className="line-kind">
                      {total} promises from {l.body.transcripts.length} calls: {parts.join(", ")}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="section prose" aria-labelledby="how">
        <h2 className="section-title" id="how">
          How a promise is checked
        </h2>
        <ol>
          <li>A model lists management&apos;s forward-looking statements and copies each one word for word.</li>
          <li>FINN keeps a statement only if those exact words are in the transcript, and takes its page from the text.</li>
          <li>A figure is kept only if it appears in the quote; segment targets and adjusted figures are marked as such.</li>
          <li>Code computes the result for the period from the company&apos;s quarterly XBRL filings and compares it with the promise.</li>
        </ol>
      </section>
    </main>
  );
}
