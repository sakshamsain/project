import Link from "next/link";
import Masthead from "@/components/Masthead";
import MarkSeen from "@/components/MarkSeen";
import { fmtClock, fmtDay, istDay } from "@/lib/format";
import { getInbox, inboxSeenAt } from "@/lib/inbox";
import { currentProfile } from "@/lib/profile";

export const dynamic = "force-dynamic";

const PUSHED: Record<string, string> = {
  sent: "Pushed",
  held: "Held for quiet hours",
  queued: "Push queued",
  failed: "Push failed",
};

export default async function InboxPage() {
  const profile = await currentProfile();
  const [items, seen] = await Promise.all([getInbox(profile.id), inboxSeenAt(profile.id)]);
  const since = profile.isDemo || !seen ? Date.now() - 86_400_000 : Date.parse(seen);
  const days = new Map<string, typeof items>();
  for (const i of items) days.set(istDay(i.at), [...(days.get(istDay(i.at)) ?? []), i]);
  return (
    <main className="page">
      <Masthead user={profile.user} note="Inbox" />
      <section className="triage" aria-label="Inbox">
        <h1 className="triage-line" style={{ fontSize: "clamp(1.8rem, 7vw, 2.4rem)" }}>
          Alerts
        </h1>
        <p className="triage-sub">
          Front-page filings on your holdings and end-of-day moves past your limits, for the last two weeks.
          This list fills whether or not push is on.
        </p>
      </section>
      {items.length === 0 ? (
        <p className="empty">
          Nothing in two weeks. <Link href="/settings">Check your holdings and limits</Link>.
        </p>
      ) : (
        [...days.entries()].map(([day, list]) => (
          <section className="section" key={day} aria-label={fmtDay(day)}>
            <h2 className="section-title">{fmtDay(day)}</h2>
            <ul className="lines">
              {list.map((i) => (
                <li className={`line inbox-item${Date.parse(i.at) > since ? " new" : ""}`} key={i.key}>
                  <span className={`stamp${i.kind === "move" ? " quiet" : ""}`}>{i.symbol}</span>
                  <div className="line-text">
                    <Link href={i.href}>{i.title}</Link>
                    <span className="line-kind">
                      {i.kind === "move" ? "End-of-day move" : i.detail}
                      {i.kind === "event" ? `, ${fmtClock(new Date(i.at))}` : ""}
                      {i.kind === "move" && i.detail ? `: ${i.detail}` : ""}
                      {i.pushed ? ` · ${PUSHED[i.pushed]}` : ""}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
      {!profile.isDemo && <MarkSeen />}
    </main>
  );
}
