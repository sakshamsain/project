// Whose portfolio this is. Signed in: the account's profile, on any device. Not signed
// in: this device's anonymous profile once it changes something, else the demo profile,
// so a first visit always shows a full Brief.
import { cookies, headers } from "next/headers";
import { auth, type SessionUser } from "./auth";
import { query } from "./db";

export const DEMO_PROFILE_ID = "00000000-0000-4000-8000-00000000f1a0";
const COOKIE = "finn_pid";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type Profile = { id: string; isDemo: boolean; user: SessionUser | null };

export async function sessionUser(): Promise<SessionUser | null> {
  try {
    const s = await auth.api.getSession({ headers: await headers() });
    return s?.user ? { id: s.user.id, email: s.user.email, name: s.user.name } : null;
  } catch {
    return null;
  }
}

async function deviceProfileId(): Promise<string | null> {
  const v = (await cookies()).get(COOKIE)?.value;
  return v && UUID.test(v) && v !== DEMO_PROFILE_ID ? v : null;
}

async function copyDemoInto(id: string): Promise<void> {
  await query(
    "insert into holdings (profile_id, isin, weight) select $1, isin, weight from holdings where profile_id = $2 on conflict do nothing",
    [id, DEMO_PROFILE_ID],
  );
}

/** The account's profile: an existing one, this device's anonymous one (claimed), or a
 *  new copy of the demo portfolio. */
async function profileForUser(userId: string): Promise<string> {
  const [own] = await query<{ id: string }>("select id from profiles where user_id = $1", [userId]);
  if (own) return own.id;
  const device = await deviceProfileId();
  if (device) {
    const [claimed] = await query<{ id: string }>(
      "update profiles set user_id = $1 where id = $2 and user_id is null and not is_demo returning id",
      [userId, device],
    );
    if (claimed) return claimed.id;
  }
  const [created] = await query<{ id: string }>(
    "insert into profiles (user_id) values ($1) on conflict (user_id) do nothing returning id",
    [userId],
  );
  if (created) {
    await copyDemoInto(created.id);
    return created.id;
  }
  const [again] = await query<{ id: string }>("select id from profiles where user_id = $1", [userId]);
  return again.id;
}

export async function currentProfile(): Promise<Profile> {
  const user = await sessionUser();
  if (user) return { id: await profileForUser(user.id), isDemo: false, user };
  const device = await deviceProfileId();
  if (device) {
    // A profile that belongs to an account is not shown to whoever holds the device next.
    const rows = await query<{ id: string }>("select id from profiles where id = $1 and user_id is null", [device]);
    if (rows.length) return { id: device, isDemo: false, user: null };
  }
  return { id: DEMO_PROFILE_ID, isDemo: true, user: null };
}

/** The profile to change. Only callable where cookies can be set (actions, routes). */
export async function ownProfile(): Promise<string> {
  const p = await currentProfile();
  if (!p.isDemo) return p.id;
  const [row] = await query<{ id: string }>("insert into profiles default values returning id");
  await copyDemoInto(row.id);
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
