// Dates in IST and numbers as the app prints them. Formatting only: every figure shown
// was computed by the worker or by SQL; nothing here does arithmetic a user relies on
// beyond rounding for display.

export const IST = "Asia/Kolkata";

const dayFmt = new Intl.DateTimeFormat("en-CA", { timeZone: IST, year: "numeric", month: "2-digit", day: "2-digit" });
const timeFmt = new Intl.DateTimeFormat("en-GB", { timeZone: IST, hour: "2-digit", minute: "2-digit", hour12: false });
const weekdayFmt = new Intl.DateTimeFormat("en-GB", { timeZone: IST, weekday: "short" });
const shortDateFmt = new Intl.DateTimeFormat("en-GB", { timeZone: IST, day: "numeric", month: "short" });
const longDateFmt = new Intl.DateTimeFormat("en-GB", { timeZone: IST, weekday: "long", day: "numeric", month: "long" });

export function toDate(v: Date | string): Date {
  return v instanceof Date ? v : new Date(v);
}

/** yyyy-mm-dd of the instant in IST. */
export function istDay(v: Date | string): string {
  return dayFmt.format(toDate(v));
}

function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000);
}

/** "18:40" today, "Yesterday 18:40", "Sat 18:40" this week, else "7 Nov 18:40". */
export function fmtWhen(v: Date | string, now: Date = new Date()): string {
  const d = toDate(v);
  const ago = daysBetween(istDay(d), istDay(now));
  const t = timeFmt.format(d);
  if (ago <= 0) return t;
  if (ago === 1) return `Yesterday ${t}`;
  if (ago < 7) return `${weekdayFmt.format(d)} ${t}`;
  return `${shortDateFmt.format(d)} ${t}`;
}

/** "Wed 11 Nov" for a calendar date (a yyyy-mm-dd string or a Date at IST midnight). */
export function fmtDay(v: Date | string): string {
  const d = typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v) ? new Date(`${v}T12:00:00+05:30`) : toDate(v);
  return `${weekdayFmt.format(d)} ${shortDateFmt.format(d)}`;
}

export function fmtLongDate(v: Date = new Date()): string {
  return longDateFmt.format(v);
}

export function fmtClock(v: Date = new Date()): string {
  return timeFmt.format(v);
}

const MINUS = "−";

/** Signed percent with a real minus sign: "+2.1%", "−6.0%". */
export function fmtPct(x: number, digits = 1): string {
  const s = Math.abs(x).toFixed(digits);
  if (Number(s) === 0) return `${s}%`;
  return `${x < 0 ? MINUS : "+"}${s}%`;
}

export function fmtMultiple(x: number): string {
  return `${x.toFixed(1)}×`;
}

export function fmtPrice(x: number): string {
  return `₹${x.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function fmtScore(x: number): string {
  return x.toFixed(2);
}

export type WindowKey = "24h" | "3d" | "7d" | "30d";

export const WINDOWS: { key: WindowKey; label: string; phrase: string; hours: number }[] = [
  { key: "24h", label: "24 hours", phrase: "in the last 24 hours", hours: 24 },
  { key: "3d", label: "3 days", phrase: "in the last 3 days", hours: 72 },
  { key: "7d", label: "7 days", phrase: "in the last 7 days", hours: 168 },
  { key: "30d", label: "30 days", phrase: "in the last 30 days", hours: 720 },
];

export function parseWindow(w: string | undefined, now: Date = new Date()) {
  const win = WINDOWS.find((x) => x.key === w) ?? WINDOWS[0];
  return { ...win, from: new Date(now.getTime() - win.hours * 3_600_000), to: now };
}
