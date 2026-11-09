import Link from "next/link";
import Masthead from "@/components/Masthead";
import { STATUS } from "@/components/Ledger";
import { sessionUser } from "@/lib/profile";
import { listLedgers, type LedgerStatus } from "@/lib/research";
import { requestLedger } from "./actions";

export const dynamic = "force-dynamic";
export const metadata = { title: "Research" };

const SHOWN: LedgerStatus[] = ["delivered", "on_track", "off_track", "missed", "not_measurable"];

const ERRORS: Record<string, string> = {
  symbol: "Type an NSE symbol, such as TCS or ASIANPAINT.",
  unknown: "That symbol is not listed on NSE.",
  limit: "This device has asked for 10 new dossiers today; dossiers already built stay open to all.",
};

export default async function Research({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; q?: string }>;
}) {
  const { error, q } = await searchParams;
  const [ledgers, user] = await Promise.all([listLedgers(), sessionUser()]);
  return (
    <main className="page">
      <Masthead user={user} note="Research" />
      <section className="triage">
        <p className="triage-line" style={{ fontSize: "clamp(1.9rem, 8vw, 2.6rem)" }}>
          What management promised,
          <br />
          <span className="kept">and what it delivered</span>
        </p>
        <p className="triage-sub">
          A dossier on any NSE company from what it filed: its last four earnings-call transcripts and
          its last two annual reports. Every promise, figure and risk is quoted with its page and
          checked; nothing else goes in, no news and no broker notes.
        </p>
      </section>

      <section className="section" aria-labelledby="build">
        <h2 className="section-title" id="build">
          Any NSE company
        </h2>
        <form action={requestLedger} className="row-form" style={{ marginBottom: "0.5rem" }}>
          <label className="visually-hidden" htmlFor="symbol">
            NSE symbol
          </label>
          <input
            id="symbol"
            name="symbol"
            type="text"
            placeholder="NSE symbol, e.g. TCS"
            defaultValue={q ?? ""}
            autoCapitalize="characters"
            autoComplete="off"
            required
          />
          <button className="button" type="submit">
            Build dossier
          </button>
        </form>
        {error && ERRORS[error] && <p className="notice">{ERRORS[error]}</p>}
        <p className="section-note">
          FINN reads the company&apos;s last four call transcripts, its last two annual reports and its
          filed results; it takes two to three minutes.
        </p>
      </section>

      <section className="section" aria-labelledby="ledgers">
        <h2 className="section-title" id="ledgers">
          Dossiers <span className="n">{ledgers.length}</span>
        </h2>
        {ledgers.length === 0 ? (
          <p className="empty">No dossiers built yet.</p>
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
          How the dossier is checked
        </h2>
        <ol>
          <li>A model lists management&apos;s forward-looking statements and copies each one word for word.</li>
          <li>FINN keeps a statement only if those exact words are in the transcript, and takes its page from the text.</li>
          <li>A figure is kept only if it appears in the quote; segment targets and adjusted figures are marked as such.</li>
          <li>Code computes the result for the period from the company&apos;s quarterly XBRL filings and compares it with the promise.</li>
          <li>From the annual reports, figures are copied by a model and kept only where code finds them in the right row of the statement; code then adds them up, and a year whose cash flows do not reconcile shows no figures at all.</li>
          <li>The bull and bear case is written only from those checked facts, and a point is dropped if it states a figure its facts do not contain.</li>
        </ol>
      </section>
    </main>
  );
}
