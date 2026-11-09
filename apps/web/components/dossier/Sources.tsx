import type { SourcesBody } from "@/lib/dossier";
import { fmtDay } from "@/lib/format";
import type { TranscriptEntry } from "@/lib/research";

const PART: Record<string, string> = {
  profit_and_loss: "Profit and loss",
  cash_flow: "Cash flows",
  auditor: "Auditor's report",
  business: "BRSR Section A",
  mdna: "MD&A",
};

function range(pages: number[]): string {
  if (pages.length === 0) return "";
  const lo = Math.min(...pages);
  const hi = Math.max(...pages);
  return lo === hi ? `p. ${lo}` : `pp. ${lo}–${hi}`;
}

export default function Sources({
  reports,
  transcripts,
  builtOn,
}: {
  reports?: SourcesBody;
  transcripts: TranscriptEntry[];
  builtOn: string | null;
}) {
  return (
    <>
      <section className="section" aria-labelledby="ars">
        <h2 className="section-title" id="ars">
          Annual reports
        </h2>
        {!reports || reports.reports.length === 0 ? (
          <p className="empty">No annual reports read yet.</p>
        ) : (
          <ul className="lines">
            {reports.reports.map((r) => (
              <li className="line" key={r.url} style={{ gridTemplateColumns: "1fr" }}>
                <div className="line-text">
                  <a href={r.url} target="_blank" rel="noopener noreferrer">
                    Annual report {r.fiscal_year}
                    {r.revised ? " (revised)" : ""}
                  </a>
                  <span className="line-kind">
                    {r.filed_on ? `Filed ${fmtDay(r.filed_on)}, ` : ""}
                    {r.status === "read" ? `${r.pages} pages, ${r.basis ?? ""} statements` : r.status}
                  </span>
                  {r.status === "read" && (
                    <span className="line-kind">
                      {Object.entries(r.sections)
                        .filter(([k, v]) => PART[k] && v.length > 0)
                        .map(([k, v]) => (
                          <a key={k} className="part" href={`${r.url}#page=${Math.min(...v)}`} target="_blank" rel="noopener noreferrer">
                            {PART[k]} {range(v)}
                          </a>
                        ))}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="section" aria-labelledby="calls">
        <h2 className="section-title" id="calls">
          Earnings calls
        </h2>
        <ul className="lines">
          {transcripts.map((t) => (
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
      </section>
      <p className="section-note">
        FINN reads only what the company filed with NSE: no news, broker notes or outside data.
        {builtOn ? ` Built ${fmtDay(builtOn.slice(0, 10))}.` : ""}
      </p>
    </>
  );
}
