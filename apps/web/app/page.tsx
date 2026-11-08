import Link from "next/link";
import Masthead from "@/components/Masthead";
import { Line, Routine, Story } from "@/components/brief";
import Intro from "@/components/Intro";
import { WINDOWS, fmtClock, fmtDay, parseWindow } from "@/lib/format";
import { currentProfile } from "@/lib/profile";
import { countHoldings, getBrief, getComingUp } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function Today({ searchParams }: { searchParams: Promise<{ w?: string }> }) {
  const { w } = await searchParams;
  let win = parseWindow(w);
  const profile = await currentProfile();
  let [rows, upcoming, holdings] = await Promise.all([
    getBrief(profile.id, win.from, win.to),
    getComingUp(profile.id),
    countHoldings(profile.id),
  ]);
  // A quiet day (a weekend, a holiday) widens the default window rather than show nothing.
  let widened = false;
  if (!w && rows.reduce((n, r) => n + r.filing_count, 0) < 3) {
    win = parseWindow("3d");
    rows = await getBrief(profile.id, win.from, win.to);
    widened = true;
  }
  const front = rows.filter((r) => r.tier === "front");
  const brief = rows.filter((r) => r.tier === "oneliner");
  const routine = rows.filter((r) => r.tier === "folded");
  const filings = rows.reduce((n, r) => n + r.filing_count, 0);
  const results = upcoming.filter((m) => m.is_results);

  return (
    <main className="page">
      <Masthead user={profile.user} note={`${fmtDay(new Date())}, ${fmtClock()} IST`} />

      <Intro />
      <section className="triage" aria-label="Summary">
        {filings === 0 ? (
          <p className="triage-line">Nothing filed</p>
        ) : (
          <p className="triage-line">
            <span className="count">{filings}</span> {filings === 1 ? "filing" : "filings"} in,
            <br />
            <span className="kept">
              <span className="count">{front.length === 0 ? "none" : front.length}</span> worth reading
              first
            </span>
          </p>
        )}
        <p className="triage-sub">
          {filings === 0
            ? `None of your ${holdings} companies filed anything ${win.phrase}. Try a longer window.`
            : `From your ${holdings} companies ${win.phrase}, ranked by how much each could move the stock. Routine filings are folded at the end.`}
          {widened && " It was a quiet day, so this shows the last 3 days."}
          {profile.isDemo && (
            <>
              {" "}
              This is the demo portfolio; <Link href="/settings">make it yours</Link>.
            </>
          )}
        </p>
      </section>

      <nav aria-label="Time window">
        <ul className="windows">
          {WINDOWS.map((x) => (
            <li key={x.key}>
              <Link
                href={x.key === "24h" ? "/" : `/?w=${x.key}`}
                aria-current={x.key === win.key ? "page" : undefined}
              >
                {x.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      {front.length > 0 && (
        <section className="section" aria-labelledby="front">
          <h2 className="section-title" id="front">
            Read first <span className="n">{front.length}</span>
          </h2>
          <div className="front">
            {front.map((r) => (
              <Story key={r.event_id} r={r} />
            ))}
          </div>
        </section>
      )}

      {brief.length > 0 && (
        <section className="section" aria-labelledby="brief">
          <h2 className="section-title" id="brief">
            In brief <span className="n">{brief.length}</span>
          </h2>
          <ul className="lines">
            {brief.map((r) => (
              <Line key={r.event_id} r={r} />
            ))}
          </ul>
        </section>
      )}

      {results.length > 0 && (
        <section className="section" aria-labelledby="dates">
          <h2 className="section-title" id="dates">
            Results dates
          </h2>
          <ul className="calendar">
            {results.map((m) => (
              <li key={`${m.symbol}-${m.meeting_date}`}>
                <Link className="stamp" href={`/company/${encodeURIComponent(m.symbol)}`}>
                  {m.symbol}
                </Link>
                <span className="day">{fmtDay(m.meeting_date)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {routine.length > 0 && (
        <section className="section" aria-label="Routine filings">
          <Routine rows={routine} />
        </section>
      )}
    </main>
  );
}
