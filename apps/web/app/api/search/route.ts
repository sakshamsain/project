import { NextResponse } from "next/server";
import { searchCompanies } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const q = new URL(req.url).searchParams.get("q") ?? "";
  if (q.trim().length < 1) return NextResponse.json({ results: [] });
  return NextResponse.json({ results: await searchCompanies(q) });
}
