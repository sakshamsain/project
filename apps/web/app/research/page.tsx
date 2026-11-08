import Link from "next/link";

export const metadata = { title: "Research" };

export default function Research() {
  return (
    <main className="page prose">
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
          The dossier for any NSE company reads only its annual reports and earnings-call
          transcripts. Every guidance statement is quoted with its page, then checked against the
          reported numbers a quarter or a year later.
        </p>
      </section>
      <p className="notice">
        Dossiers are being built this week. Until they are, each company page shows its filings
        and prices.
      </p>
      <h2>How a dossier is made</h2>
      <ol>
        <li>Collect the last two annual reports and the last four call transcripts from the exchange.</li>
        <li>Pull out each forward-looking statement with the speaker, the page and the exact words.</li>
        <li>Match it to the reported figure for the period it was about, computed from the filings.</li>
        <li>Mark it delivered, missed, on track or too early to say; drop anything that cannot be measured.</li>
      </ol>
    </main>
  );
}
