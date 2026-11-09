import Link from "next/link";
import Cite from "@/components/dossier/Cite";
import { METRIC, STATUS } from "@/components/Ledger";
import { fmtDay } from "@/lib/format";
import type { LedgerCheck as Check } from "@/lib/queries";

const ORDER = ["missed", "off_track", "on_track", "delivered"] as const;

function label(p: Check["measured"][number]): string {
  const m = (p.metric_key && METRIC[p.metric_key]) || p.metric;
  return m.charAt(0).toUpperCase() + m.slice(1);
}

/** The bridge on a results event: what management promised, checked by code against
 *  the quarters now filed. */
export default function LedgerCheck({ check, symbol, fresh }: { check: Check; symbol: string; fresh: boolean }) {
  const parts = ORDER.filter((s) => check.counts[s]).map((s) => `${check.counts[s]} ${STATUS[s].toLowerCase()}`);
  const moved = new Map(check.changes.map((c) => [c.id, c.was]));
  return (
    <section className="ledger-check" aria-labelledby="against">
      <h2 className="section-title" id="against">
        Against the Promise Ledger
      </h2>
      <p className="section-note">
        {fresh ? "Checked when these results were read" : `Ledger as of ${fmtDay(check.checked_at.slice(0, 10))}`}:{" "}
        {parts.length ? parts.join(", ") : "nothing measurable yet"}.
      </p>
      <ul className="said">
        {check.measured.slice(0, 4).map((p) => (
          <li key={p.id}>
            <span className="said-when">
              {label(p)}
              {p.period ? `, ${p.period}` : ""}{" "}
              <span className={`chip ${p.status}`}>{STATUS[p.status]}</span>
              {moved.get(p.id) ? (
                <span className="rev changed"> was {STATUS[moved.get(p.id) as keyof typeof STATUS]?.toLowerCase()}</span>
              ) : null}
            </span>
            {p.note && <span className="ledger-note">{p.note.replace(/\.+$/, "")}.</span>}
            <q>{p.quote}</q> <Cite doc={p.document_id} page={p.page} quote={p.quote} />
          </li>
        ))}
      </ul>
      <p className="section-note" style={{ marginTop: "0.5rem" }}>
        <Link href={`/research/${encodeURIComponent(symbol)}?tab=promises`}>The full ledger</Link>
      </p>
    </section>
  );
}
