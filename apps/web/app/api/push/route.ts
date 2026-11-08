import { NextResponse } from "next/server";
import { query } from "@/lib/db";
import { ownProfile } from "@/lib/profile";
import { validEndpoint } from "@/lib/push";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => null)) as
    | { endpoint?: unknown; keys?: { p256dh?: unknown; auth?: unknown } }
    | null;
  const p256dh = body?.keys?.p256dh;
  const auth = body?.keys?.auth;
  if (!validEndpoint(body?.endpoint) || typeof p256dh !== "string" || typeof auth !== "string") {
    return NextResponse.json({ error: "Not a push subscription" }, { status: 400 });
  }
  const profile = await ownProfile();
  await query(
    `insert into push_subscriptions (profile_id, endpoint, p256dh, auth) values ($1, $2, $3, $4)
     on conflict (endpoint) do update set profile_id = excluded.profile_id,
       p256dh = excluded.p256dh, auth = excluded.auth`,
    [profile, body!.endpoint, p256dh.slice(0, 200), auth.slice(0, 100)],
  );
  return NextResponse.json({ ok: true });
}

export async function DELETE(req: Request) {
  const body = (await req.json().catch(() => null)) as { endpoint?: unknown } | null;
  if (!validEndpoint(body?.endpoint)) {
    return NextResponse.json({ error: "Not a push subscription" }, { status: 400 });
  }
  const profile = await ownProfile();
  await query("delete from push_subscriptions where endpoint = $1 and profile_id = $2", [
    body!.endpoint,
    profile,
  ]);
  return NextResponse.json({ ok: true });
}
