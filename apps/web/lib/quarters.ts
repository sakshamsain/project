import type { QuarterPoint } from "@/components/charts/QuarterChart";

/** Quarterly rows from `financials` as chart points, oldest first, the last eight. */
export function series(rows: { period: string; metric: string; value: number }[], metric: string): QuarterPoint[] {
  return rows
    .filter((r) => r.metric === metric)
    .map((r) => {
      const m = /^Q([1-4])FY(\d{2})$/.exec(r.period);
      return m ? { label: `Q${m[1]} FY${m[2]}`, q: Number(m[1]), fy: Number(m[2]), value: r.value } : null;
    })
    .filter((p): p is QuarterPoint => p !== null)
    .sort((a, b) => a.fy - b.fy || a.q - b.q)
    .slice(-8);
}
