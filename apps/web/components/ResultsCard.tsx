import { fmtPct } from "@/lib/format";

export type ResultsCardData = {
  status: "ok" | "needs_a_look" | "waiting" | "unsupported" | "error";
  lender?: boolean;
  period?: string;
  months?: string;
  basis?: string;
  audited?: string | null;
  rows?: { name: string; value: number; qoq_pct: number | null; yoy_pct: number | null }[];
  margin_label?: string;
  margin_pct?: number | null;
  margin_qoq_bps?: number | null;
  margin_yoy_bps?: number | null;
  flags?: string[];
  compared_with?: { previous_quarter: string | null; year_ago: string | null };
  sources?: { current?: string };
  consistency_failures?: string[];
};

function crore(x: number): string {
  return x.toLocaleString("en-IN", { maximumFractionDigits: Math.abs(x) >= 100 ? 0 : 1 });
}

function Change({ v }: { v: number | null }) {
  if (v == null) return <td className="na">n/a</td>;
  return <td className={v < 0 ? "down" : "up"}>{fmtPct(v)}</td>;
}

function bps(v: number | null | undefined): string | null {
  if (v == null) return null;
  const r = Math.round(v);
  return `${r < 0 ? "−" : "+"}${Math.abs(r)} bps`;
}

export default function ResultsCard({ card, filingUrl }: { card: ResultsCardData; filingUrl?: string | null }) {
  const link = card.sources?.current ?? filingUrl ?? null;
  if (card.status === "needs_a_look" || card.status === "error") {
    return (
      <p className="notice">
        Numbers need a look: the filed figures do not add up, so FINN is not showing them.{" "}
        {link && (
          <a href={filingUrl ?? link} target="_blank" rel="noopener noreferrer">
            Read the filing
          </a>
        )}
      </p>
    );
  }
  if (card.status !== "ok" || !card.rows) return null;
  const margin = [
    card.margin_pct != null ? `${card.margin_pct.toFixed(1)}%` : null,
    bps(card.margin_qoq_bps) && `${bps(card.margin_qoq_bps)} QoQ`,
    bps(card.margin_yoy_bps) && `${bps(card.margin_yoy_bps)} YoY`,
  ].filter(Boolean);
  return (
    <figure className="results">
      <figcaption>
        {card.period} ({card.months}), {card.basis?.toLowerCase()}
        {card.audited ? `, ${card.audited.toLowerCase()}` : ""}
      </figcaption>
      <table>
        <thead>
          <tr>
            <th scope="col">
              <span className="visually-hidden">Line</span>
            </th>
            <th scope="col">&#8377; crore</th>
            <th scope="col" title={card.compared_with?.previous_quarter ?? undefined}>
              QoQ
            </th>
            <th scope="col" title={card.compared_with?.year_ago ?? undefined}>
              YoY
            </th>
          </tr>
        </thead>
        <tbody>
          {card.rows.map((r) => (
            <tr key={r.name}>
              <th scope="row">{r.name.startsWith("EBITDA") ? "EBITDA*" : r.name}</th>
              <td>{crore(r.value)}</td>
              <Change v={r.qoq_pct} />
              <Change v={r.yoy_pct} />
            </tr>
          ))}
        </tbody>
      </table>
      {margin.length > 0 && (
        <p className="results-note">
          {card.margin_label?.replace("EBITDA (excl. other income)", "EBITDA")}: {margin.join(", ")}
        </p>
      )}
      {card.flags?.map((f) => (
        <p className="results-note flag" key={f}>
          {f}
        </p>
      ))}
      <p className="results-note fine">
        {card.lender
          ? "NII is interest earned less interest paid; PPOP is operating profit before provisions. "
          : "*Profit before exceptional items and tax, plus finance costs and depreciation, less other income; it can differ from the EBITDA in a press release. "}
        Computed by FINN from the company&apos;s XBRL filing on NSE.
      </p>
    </figure>
  );
}
