import Link from "next/link";
import Masthead from "@/components/Masthead";
import { Ticker } from "@/components/brief";
import { fmtDay, fmtMultiple, fmtPct } from "@/lib/format";
import { categoryLabel } from "@/lib/labels";
import { currentProfile } from "@/lib/profile";
import { getPulse, getThresholds, type Hit, type Move } from "@/lib/queries";

export const dynamic = "force-dynamic";
export const metadata = { title: "Pulse" };

function describe(h: Hit): string {
  switch (h.kind) {
    case "volume_multiple":
      return `volume ${fmtMultiple(h.value)} the 20-day average`;
    case "price_move":
      return `price ${fmtPct(h.value)}`;
    case "sigma_move":
      return `${Math.abs(h.zscore ?? 0).toFixed(1)} standard deviations from its usual daily move`;
    case "delivery_spike":
      return `${h.value.toFixed(1)}% of shares taken for delivery`;
    default:
      return h.kind;
  }
}

/** The closes leading up to the move, the move's own session marked: enough to see
 *  whether it broke a trend or continued one. */
function Spark({ closes, up }: { closes: number[]; up: boolean }) {
  if (closes.length < 5) return null;
  const lo = Math.min(...closes);
  const hi = Math.max(...closes);
  const span = hi - lo || 1;
  const x = (i: number) => 2 + (i / (closes.length - 1)) * 100;
  const y = (v: number) => 38 - ((v - lo) / span) * 34;
  const d = closes.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const last = closes.length - 1;
  return (
    <svg className="spark" viewBox="0 0 104 42" role="img" aria-label={`Last ${closes.length} closes`}>
      <path className="trail" d={d} />
      <circle className={`now ${up ? "up" : "down"}`} cx={x(last)} cy={y(closes[last])} r="4" />
    </svg>
  );
}

function MoveRow({ m }: { m: Move }) {
  const ret = m.return_pct;
  const facts = m.hits.filter((h) => h.kind !== "price_move");
  return (
    <li className="move">
      <div className="move-head">
        <Ticker symbol={m.symbol} />
        {ret != null && (
          <span className={`move-ret ${ret < 0 ? "down" : "up"}`}>
            {ret < 0 ? "▼" : "▲"} {fmtPct(ret)}
          </span>
        )}
      </div>
      {m.closes && ret != null && <Spark closes={m.closes} up={ret >= 0} />}
      <p className="move-facts">
        {facts.length ? facts.map((h) => describe(h)).join("; ") : "Price move past your limit"}
      </p>
      {m.linked_event_id ? (
        <p className="move-why">
          Filed that session:{" "}
          <Link href={`/event/${m.linked_event_id}`}>{m.linked_headline ?? "Exchange filing"}</Link>
          {m.linked_category ? ` (${categoryLabel(m.linked_category)})` : ""}
        </p>
      ) : (
        <p className="move-why none">No filing found for this session.</p>
      )}
    </li>
  );
}

export default async function Pulse() {
  const profile = await currentProfile();
  const t = await getThresholds(profile.id);
  const { days, moves } = await getPulse(profile.id, t, 5);
  return (
    <main className="page">
      <Masthead user={profile.user} note="Pulse" />

      <section className="triage" aria-label="Summary">
        <p className="triage-line" style={{ fontSize: "clamp(1.9rem, 8vw, 2.6rem)" }}>
          <span className="count">{moves.length}</span> unusual {moves.length === 1 ? "move" : "moves"}
          <br />
          <span className="kept">in the last {days.length} sessions</span>
        </p>
        <p className="triage-sub">
          A holding shows up here when its volume reaches {fmtMultiple(t.volume)} its 20-day average,
          its price moves {t.price}% in a day, or the move is {t.sigma} standard deviations from
          normal. <Link href="/settings#alerts">Change the limits</Link>.
        </p>
      </section>

      {days.map((d) => {
        const today = moves.filter((m) => m.trade_date === d);
        const index = today.find((m) => m.index_change_pct != null)?.index_change_pct;
        return (
          <section className="section" key={d} aria-label={fmtDay(d)}>
            <h2 className="section-title">
              {fmtDay(d)}
              {index != null && <span className="n">Nifty {fmtPct(index)}</span>}
            </h2>
            {today.length === 0 ? (
              <p className="empty">No holding moved past your limits.</p>
            ) : (
              <ul className="lines">
                {today.map((m) => (
                  <MoveRow key={`${m.isin}-${d}`} m={m} />
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </main>
  );
}
