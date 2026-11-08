"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { query } from "@/lib/db";
import { ownProfile } from "@/lib/profile";
import { DEFAULT_THRESHOLDS, FLOORS, saveThresholds, type Thresholds } from "@/lib/queries";

const ISIN = /^IN[A-Z0-9]{10}$/;

function back(form: FormData, fallback = "/settings"): string {
  const b = String(form.get("back") ?? "");
  return b.startsWith("/") && !b.startsWith("//") ? b : fallback;
}

export async function addHolding(form: FormData) {
  const isin = String(form.get("isin") ?? "");
  if (!ISIN.test(isin)) return;
  const id = await ownProfile();
  await query(
    "insert into holdings (profile_id, isin) select $1, isin from companies where isin = $2 on conflict do nothing",
    [id, isin],
  );
  revalidatePath("/", "layout");
  redirect(back(form));
}

export async function removeHolding(form: FormData) {
  const isin = String(form.get("isin") ?? "");
  if (!ISIN.test(isin)) return;
  const id = await ownProfile();
  await query("delete from holdings where profile_id = $1 and isin = $2", [id, isin]);
  revalidatePath("/", "layout");
  redirect(back(form));
}

export async function resetToDemo() {
  const id = await ownProfile();
  await query("delete from holdings where profile_id = $1", [id]);
  await query(
    "insert into holdings (profile_id, isin, weight) select $1, isin, weight from holdings where profile_id = '00000000-0000-4000-8000-00000000f1a0'",
    [id],
  );
  revalidatePath("/", "layout");
  redirect("/settings");
}

export async function updateThresholds(form: FormData) {
  const read = (k: keyof Thresholds) => {
    const v = Number(form.get(k));
    return Number.isFinite(v) && v > 0 ? Math.max(FLOORS[k], v) : DEFAULT_THRESHOLDS[k];
  };
  const id = await ownProfile();
  await saveThresholds(id, {
    volume: read("volume"),
    price: read("price"),
    sigma: read("sigma"),
    delivery: read("delivery"),
  });
  revalidatePath("/", "layout");
  redirect("/settings?saved=alerts");
}
