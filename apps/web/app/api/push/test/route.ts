import { NextResponse } from "next/server";
import webpush from "web-push";
import { query } from "@/lib/db";
import { categoryLabel } from "@/lib/labels";
import { currentProfile } from "@/lib/profile";
import { validEndpoint } from "@/lib/push";

// Replays the latest front-page filing on this device, so a reviewer can see an alert
// without waiting for the market. At most one test every 30 seconds per profile.
export async function POST() {
  const profile = await currentProfile();
  if (profile.isDemo) {
    return NextResponse.json({ error: "Turn on notifications first." }, { status: 400 });
  }
  const pub = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;
  const priv = process.env.VAPID_PRIVATE_KEY;
  const subject = process.env.VAPID_SUBJECT;
  if (!pub || !priv || !subject) {
    return NextResponse.json({ error: "Notifications are not set up on this server." }, { status: 503 });
  }
  const slot = await query(
    `insert into notifications (profile_id, dedupe_key, channel, status, sent_at)
     values ($1, 'test:' || floor(extract(epoch from now()) / 30)::bigint, 'push', 'sent', now())
     on conflict do nothing returning id`,
    [profile.id],
  );
  if (slot.length === 0) {
    return NextResponse.json({ error: "One test every 30 seconds. Try again shortly." }, { status: 429 });
  }
  const subs = await query<{ id: string; endpoint: string; p256dh: string; auth: string }>(
    "select id::text, endpoint, p256dh, auth from push_subscriptions where profile_id = $1",
    [profile.id],
  );
  if (subs.length === 0) {
    return NextResponse.json({ error: "This device has no notification subscription." }, { status: 400 });
  }
  const [e] = await query<{ event_id: string; symbol: string | null; headline: string | null; category: string; stage: string | null }>(
    `select b.event_id::text, b.symbol, b.headline, b.category, b.stage
       from brief($1, now() - interval '30 days', now()) b
      where b.tier = 'front' order by b.first_seen_at desc limit 1`,
    [profile.id],
  );
  const payload = e
    ? {
        title: `${e.symbol ?? "FINN"}: ${categoryLabel(e.category, e.stage)}`,
        body: e.headline ?? "New filing",
        url: `/event/${e.event_id}`,
        tag: "finn-test",
      }
    : { title: "FINN", body: "Notifications are working on this device.", url: "/", tag: "finn-test" };

  webpush.setVapidDetails(subject, pub, priv);
  let sent = 0;
  for (const s of subs) {
    if (!validEndpoint(s.endpoint)) continue;
    try {
      await webpush.sendNotification(
        { endpoint: s.endpoint, keys: { p256dh: s.p256dh, auth: s.auth } },
        JSON.stringify(payload),
        { TTL: 600 },
      );
      sent += 1;
    } catch (err) {
      const status = (err as { statusCode?: number }).statusCode;
      if (status === 404 || status === 410) {
        await query("delete from push_subscriptions where id = $1", [s.id]);
      }
    }
  }
  if (sent === 0) {
    return NextResponse.json({ error: "The push service refused the notification. Turn notifications off and on again." }, { status: 502 });
  }
  return NextResponse.json({ ok: true, sent, replayed: Boolean(e) });
}
