import { NextResponse } from "next/server";
import { getInbox, inboxSeenAt, markInboxSeen, unread } from "@/lib/inbox";
import { currentProfile } from "@/lib/profile";

export const dynamic = "force-dynamic";

/** The unread count for the tab bar badge. */
export async function GET() {
  const profile = await currentProfile();
  const [items, seen] = await Promise.all([getInbox(profile.id), inboxSeenAt(profile.id)]);
  return NextResponse.json({ unread: unread(items, profile.isDemo ? null : seen) });
}

/** Marks the inbox seen (not for the shared demo profile). */
export async function POST() {
  const profile = await currentProfile();
  if (!profile.isDemo) await markInboxSeen(profile.id);
  return NextResponse.json({ ok: true });
}
