// The inbox: everything FINN would alert this profile about, push or no push. Front-page
// events on its holdings and end-of-day moves past its own thresholds, newest first.
import { query } from "./db";
import { categoryLabel } from "./labels";
import { getPulse, getThresholds } from "./queries";

export type InboxItem = {
  key: string;
  kind: "event" | "move";
  at: string; // ISO time: filing time, or the session's close for a move
  symbol: string;
  title: string;
  detail: string | null;
  href: string;
  pushed: "sent" | "held" | "queued" | "failed" | null;
};

const DAYS = 14;

export async function getInbox(profileId: string): Promise<InboxItem[]> {
  const [events, thresholds, pushed] = await Promise.all([
    query<{
      id: string;
      headline: string | null;
      category: string;
      stage: string | null;
      at: string;
      symbol: string;
      status: InboxItem["pushed"];
    }>(
      `select e.id::text, e.headline, e.category, e.stage, e.first_seen_at::text as at,
              coalesce((select a.value from company_aliases a where a.isin = e.isin
                          and a.kind = 'nse_symbol' and a.valid_to is null limit 1), e.isin) as symbol,
              n.status
         from events e
         join holdings h on h.isin = e.isin and h.profile_id = $1
         left join notifications n on n.event_id = e.id and n.profile_id = $1 and n.channel = 'push'
        where e.tier = 'front' and e.first_seen_at > now() - make_interval(days => $2)
        order by e.first_seen_at desc limit 60`,
      [profileId, DAYS],
    ),
    getThresholds(profileId),
    query<{ day: string; status: InboxItem["pushed"] }>(
      `select substr(dedupe_key, 5) as day, status from notifications
        where profile_id = $1 and dedupe_key like 'eod:%' and channel = 'push'`,
      [profileId],
    ),
  ]);
  const pulse = await getPulse(profileId, thresholds, 10);
  const pushedDay = new Map(pushed.map((p) => [p.day, p.status]));
  const items: InboxItem[] = events.map((e) => ({
    key: `e${e.id}`,
    kind: "event",
    at: e.at,
    symbol: e.symbol,
    title: e.headline ?? "Exchange filing",
    detail: categoryLabel(e.category, e.stage),
    href: `/event/${e.id}`,
    pushed: e.status ?? null,
  }));
  for (const m of pulse.moves) {
    const ret = m.return_pct;
    items.push({
      key: `m${m.trade_date}${m.isin}`,
      kind: "move",
      at: `${m.trade_date}T15:30:00+05:30`,
      symbol: m.symbol,
      title:
        ret == null
          ? "Crossed your limits"
          : `${ret < 0 ? "Fell" : "Rose"} ${Math.abs(ret).toFixed(1)}%${m.linked_headline ? "" : ", no filing found"}`,
      detail: m.linked_headline,
      href: m.linked_event_id ? `/event/${m.linked_event_id}` : `/company/${encodeURIComponent(m.symbol)}`,
      pushed: pushedDay.get(m.trade_date) ?? null,
    });
  }
  return items.sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
}

/** When the profile last opened the inbox; the shared demo profile never records it. */
export async function inboxSeenAt(profileId: string): Promise<string | null> {
  const [row] = await query<{ seen: string | null }>("select inbox_seen_at::text as seen from profiles where id = $1", [
    profileId,
  ]);
  return row?.seen ?? null;
}

export async function markInboxSeen(profileId: string): Promise<void> {
  await query("update profiles set inbox_seen_at = now() where id = $1 and not is_demo", [profileId]);
}

/** New since the last look; for a profile that never looked, the last 24 hours. */
export function unread(items: InboxItem[], seenAt: string | null, now = Date.now()): number {
  const since = seenAt ? Date.parse(seenAt) : now - 86_400_000;
  return items.filter((i) => Date.parse(i.at) > since).length;
}
