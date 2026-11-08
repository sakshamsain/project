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

function MoveRow({ m }: { m: Move }) {
  const ret = m.return_pct;
  return (
    <li className="move">
      <Ticker symbol={m.symbol} />
      <div className="move-facts">
        {ret != null && (
          <span className={ret < 0 ? "down" : "up"}>
            {ret < 0 ? "▼" : "▲"} {fmtPct(ret)}
          </span>
        )}
        {m.hits
          .filter((h) => h.kind !== "price_move")
          .map((h) => (
            <span key={h.kind}>{describe(h)}</span>
          ))}
      </div>
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
