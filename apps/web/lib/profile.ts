// Anonymous profiles: each device gets its own once it changes something. Until then it
// reads the demo profile, so a reviewer sees a full Brief on the first visit.
import { cookies } from "next/headers";
import { query } from "./db";

export const DEMO_PROFILE_ID = "00000000-0000-4000-8000-00000000f1a0";
const COOKIE = "finn_pid";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type Profile = { id: string; isDemo: boolean };

export async function currentProfile(): Promise<Profile> {
  const v = (await cookies()).get(COOKIE)?.value;
  if (v && UUID.test(v) && v !== DEMO_PROFILE_ID) {
    const rows = await query<{ id: string }>("select id from profiles where id = $1", [v]);
    if (rows.length) return { id: v, isDemo: false };
  }
  return { id: DEMO_PROFILE_ID, isDemo: true };
}

/** The device's own profile, created from the demo portfolio on first use.
 *  Only callable where cookies can be set (server actions, route handlers). */
export async function ownProfile(): Promise<string> {
  const p = await currentProfile();
  if (!p.isDemo) return p.id;
  const [row] = await query<{ id: string }>("insert into profiles default values returning id");
  await query(
    "insert into holdings (profile_id, isin, weight) select $1, isin, weight from holdings where profile_id = $2",
    [row.id, DEMO_PROFILE_ID],
  );
  await query(
    "insert into alert_rules (profile_id, kind, params) select $1, kind, params from alert_rules where profile_id = $2 and isin is null",
    [row.id, DEMO_PROFILE_ID],
  );
  (await cookies()).set(COOKIE, row.id, {
    httpOnly: true,
    sameSite: "lax",
    secure: true,
    path: "/",
    maxAge: 60 * 60 * 24 * 400,
  });
  return row.id;
}
