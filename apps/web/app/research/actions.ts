"use server";

import { redirect } from "next/navigation";
import { query } from "@/lib/db";
import { ownProfile } from "@/lib/profile";

const DAILY_LIMIT = 10;

async function trigger(jobId: number): Promise<void> {
  const url = process.env.FINN_TRIGGER_URL;
  const token = process.env.FINN_TRIGGER_TOKEN;
  if (!url || !token) return; // the next poll picks the job up
  try {
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId, token }),
      signal: AbortSignal.timeout(8000),
    });
  } catch {
    // The worker's poll claims queued jobs, so a missed ping only delays the build.
  }
}

export async function requestLedger(form: FormData) {
  const raw = String(form.get("symbol") ?? "").trim().toUpperCase();
  if (!/^[A-Z0-9&\-]{1,20}$/.test(raw)) redirect("/research?error=symbol");
  const [company] = await query<{ isin: string; symbol: string }>(
    `select a.isin, a.value as symbol from company_aliases a
      where a.kind = 'nse_symbol' and a.value = $1 and a.valid_to is null limit 1`,
    [raw],
  );
  if (!company) redirect(`/research?error=unknown&q=${encodeURIComponent(raw)}`);

  const fresh = await query(
    `select 1 from dossier_sections where isin = $1 and section = 'ledger'
       and built_at > now() - interval '3 days' limit 1`,
    [company.isin],
  );
  if (fresh.length) redirect(`/research/${company.symbol}`);

  const running = await query<{ id: string }>(
    `select id::text from jobs where kind = 'dossier' and payload ->> 'symbol' = $1
       and status in ('queued', 'running') and created_at > now() - interval '20 minutes'
     order by created_at desc limit 1`,
    [company.symbol],
  );
  if (running.length) redirect(`/research/${company.symbol}?job=${running[0].id}`);

  const profile = await ownProfile();
  const [{ n }] = await query<{ n: number }>(
    `select count(*)::int as n from jobs where profile_id = $1 and kind = 'dossier'
       and created_at > now() - interval '1 day'`,
    [profile],
  );
  if (n >= DAILY_LIMIT) redirect("/research?error=limit");

  const [job] = await query<{ id: string }>(
    `insert into jobs (kind, payload, profile_id) values ('dossier', jsonb_build_object('symbol', $1::text), $2)
     returning id::text`,
    [company.symbol, profile],
  );
  await trigger(Number(job.id));
  redirect(`/research/${company.symbol}?job=${job.id}`);
}
