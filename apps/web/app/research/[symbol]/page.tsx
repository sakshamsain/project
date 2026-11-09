import Link from "next/link";
import Masthead from "@/components/Masthead";
import JobProgress from "@/components/JobProgress";
import { ThreadCard, threads } from "@/components/Ledger";
import ActiveTab from "@/components/dossier/ActiveTab";
import Case from "@/components/dossier/Case";
import Cash from "@/components/dossier/Cash";
import Snapshot from "@/components/dossier/Snapshot";
import Sources from "@/components/dossier/Sources";
import Trajectory from "@/components/dossier/Trajectory";
import { query } from "@/lib/db";
import { getPriceHead, getQuarters, getSections } from "@/lib/dossier";
import { fmtDay, fmtPct, fmtPrice } from "@/lib/format";
import { sessionUser } from "@/lib/profile";
import { getLedger, type LedgerStatus } from "@/lib/research";
import { requestLedger } from "../actions";

export const dynamic = "force-dynamic";

const MEASURED: LedgerStatus[] = ["delivered", "missed", "on_track", "off_track", "too_early"];

const TABS = [
  { key: "snapshot", label: "Snapshot" },
  { key: "trajectory", label: "Trajectory" },
  { key: "promises", label: "Promises" },
  { key: "cash", label: "Cash" },
  { key: "case", label: "Bull vs bear" },
  { key: "sources", label: "Sources" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export default async function DossierPage({
  params,
  searchParams,
}: {
  params: Promise<{ symbol: string }>;
  searchParams: Promise<{ job?: string; tab?: string }>;
}) {
  const { symbol } = await params;
  const { job, tab } = await searchParams;
  const sym = decodeURIComponent(symbol).toUpperCase();
  const [data, user] = await Promise.all([getLedger(sym), sessionUser()]);
  const jobId = job && /^\d+$/.test(job) ? job : null;
  if (!data) {
    const [c] = await query<{ name: string }>(
      `select c.name from company_aliases a join companies c on c.isin = a.isin
        where a.kind = 'nse_symbol' and a.value = $1 and a.valid_to is null limit 1`,
      [sym],
    );
    return (
      <main className="page">
        <Masthead user={user} note="Dossier" />
        <section className="triage">
          <span className="stamp">{sym}</span>
          <h1 className="triage-line dossier-name">{c?.name ?? "Not listed on NSE"}</h1>
        </section>
        {jobId ? (
          <JobProgress id={jobId} />
        ) : c ? (
          <form action={requestLedger}>
            <input type="hidden" name="symbol" value={sym} />
            <p className="section-note">
              No dossier yet. FINN reads the last four earnings-call transcripts and the last two annual reports filed
              with NSE; it takes two to three minutes.
            </p>
            <button className="button" type="submit">
              Build dossier
            </button>
          </form>
        ) : (
          <p className="empty">Check the symbol and try again from Research.</p>
        )}
      </main>
    );
  }

  const { body, promises, company, isin } = data;
  const [{ sections, built_at }, quarters, price] = await Promise.all([
    getSections(isin),
    getQuarters(isin),
    getPriceHead(isin),
  ]);
  const current: TabKey = TABS.find((t) => t.key === tab)?.key ?? "snapshot";
  const reports = sections.annual_reports?.reports.filter((r) => r.status === "read") ?? [];
  const urls: Record<string, string> = Object.fromEntries(
    (sections.annual_reports?.reports ?? []).filter((r) => r.document_id).map((r) => [String(r.document_id), r.url]),
  );
  const read = body.transcripts.filter((t) => t.status === "read");
  const all = threads(promises);
  const checked = all.filter((t) => MEASURED.includes(t.items[0].status));
  const unchecked = all.filter((t) => !MEASURED.includes(t.items[0].status));
  const ret = price?.prev_close ? (price.close / price.prev_close - 1) * 100 : null;

  return (
    <main className="page">
      <Masthead user={user} note="Dossier" />
      {jobId && <JobProgress id={jobId} />}

      <section className="triage" aria-label="Company">
        <Link className="stamp" href={`/company/${encodeURIComponent(body.symbol)}`}>
          {body.symbol}
        </Link>
        <h1 className="triage-line dossier-name">{company}</h1>
        {price && (
          <p className="triage-sub" style={{ marginBottom: "0.25rem" }}>
            {fmtPrice(price.close)} at the close on {fmtDay(price.trade_date)}
            {ret != null && (
              <>
                , <span className={ret < 0 ? "down" : "up"}>{ret < 0 ? "▼" : "▲"} {fmtPct(ret)}</span>
              </>
            )}
          </p>
        )}
        <p className="triage-sub">
          From {reports.length ? `${reports.length === 1 ? "one annual report" : `${reports.length} annual reports`} and ` : ""}
          {read.length} earnings calls filed with NSE, and nothing else.
        </p>
        {!sections.annual_reports && (
          <form action={requestLedger} className="row-form">
            <input type="hidden" name="symbol" value={body.symbol} />
            <button className="button small" type="submit">
              Add the annual reports
            </button>
          </form>
        )}
      </section>

      <nav className="dtabs" aria-label="Dossier sections">
        <ul>
          {TABS.map((t) => (
            <li key={t.key}>
              <Link
                href={`/research/${encodeURIComponent(body.symbol)}${t.key === "snapshot" ? "" : `?tab=${t.key}`}`}
                aria-current={current === t.key ? "page" : undefined}
                scroll={false}
              >
                {t.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <ActiveTab tab={current} />

      {current === "snapshot" && (
        <Snapshot
          symbol={body.symbol}
          business={sections.business}
          cash={sections.cash}
          auditor={sections.auditor}
          counts={body.counts}
          promises={promises.length}
        />
      )}
      {current === "trajectory" && <Trajectory quarters={quarters} cash={sections.cash} />}
      {current === "cash" && <Cash cash={sections.cash} urls={urls} />}
      {current === "case" && <Case c={sections.case} auditor={sections.auditor} risks={sections.risks} />}
      {current === "sources" && (
        <Sources reports={sections.annual_reports} transcripts={body.transcripts} builtOn={built_at ?? body.built_on} />
      )}
      {current === "promises" && (
        <>
          <p className="lede-small">
            {promises.length} promises from {read.length} earnings calls. {checked.length === 0 ? "None" : checked.length}{" "}
            can be checked against the figures the company filed ({body.quarters_on_file.length} quarters,{" "}
            {body.basis?.toLowerCase() ?? "as filed"}); the rest are about things the filings do not report.
          </p>
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
                Each of these is quoted from a call; FINN cannot measure it from the quarterly statements, so it is
                tracked from call to call instead.
              </p>
              <div className="threads">
                {unchecked.map((t) => (
                  <ThreadCard key={t.key} t={t} />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}
