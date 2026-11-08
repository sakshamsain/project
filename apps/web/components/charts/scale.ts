// Shared chart arithmetic for display only: tick placement and number formatting. The
// figures charted come from the worker or from SQL.

/** Round tick values covering [lo, hi], about `count` of them. */
export function niceTicks(lo: number, hi: number, count = 4): number[] {
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [0, 1];
  if (lo === hi) {
    const pad = Math.abs(lo) * 0.05 || 1;
    lo -= pad;
    hi += pad;
  }
  const span = hi - lo;
  const raw = span / Math.max(1, count - 1);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
  const start = Math.floor(lo / step) * step;
  const end = Math.ceil(hi / step) * step;
  const out: number[] = [];
  for (let v = start; v <= end + step / 2; v += step) out.push(Number(v.toFixed(10)));
  return out;
}

/** Axis labels: full numbers under 10,000; compact above, one style per axis. */
export function axisLabel(v: number, max: number): string {
  if (Math.abs(max) >= 10_000) {
    if (Math.abs(max) >= 1e7) return `${(v / 1e7).toFixed(v % 1e7 === 0 ? 0 : 1)}Cr`;
    if (Math.abs(max) >= 1e5) return `${(v / 1e5).toFixed(v % 1e5 === 0 ? 0 : 1)}L`;
    return `${(v / 1000).toFixed(v % 1000 === 0 ? 0 : 1)}K`;
  }
  return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

/** Share volumes in Indian units: 2.56 Cr, 4.1 L, 9,870. */
export function volumeLabel(v: number): string {
  if (v >= 1e7) return `${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `${(v / 1e5).toFixed(1)} L`;
  return v.toLocaleString("en-IN");
}

export function signedPct(x: number): string {
  const s = Math.abs(x).toFixed(1);
  return Number(s) === 0 ? `${s}%` : `${x < 0 ? "−" : "+"}${s}%`;
}

/** A bar with a 4px rounded data end and a square end on the baseline. */
export function barPath(x: number, w: number, y0: number, y1: number, r = 4): string {
  const top = Math.min(y0, y1);
  const h = Math.abs(y1 - y0);
  const rr = Math.min(r, w / 2, h);
  if (h <= 0.5) return `M${x},${y0}h${w}`;
  if (y1 < y0) {
    // grows up: round the top
    return `M${x},${y0}V${top + rr}Q${x},${top} ${x + rr},${top}H${x + w - rr}Q${x + w},${top} ${x + w},${top + rr}V${y0}Z`;
  }
  // grows down (a loss): round the bottom
  const bottom = top + h;
  return `M${x},${y0}V${bottom - rr}Q${x},${bottom} ${x + rr},${bottom}H${x + w - rr}Q${x + w},${bottom} ${x + w},${bottom - rr}V${y0}Z`;
}
