"use client";

import { useEffect, useRef, useState } from "react";

const H = 46;
const PAD = 8;

function fmt(v: number, unit: string | null): string {
  if (unit === "crore") return `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })} Cr`;
  if (unit === "bps") return `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(0)} bps`;
  return `${v.toFixed(1)}%`;
}

/** The promised range as a band and the computed result as a dot, on one scale. */
export default function RangeCheck({
  low,
  high,
  actual,
  unit,
  label,
}: {
  low: number | null;
  high: number | null;
  actual: number;
  unit: string | null;
  label: string;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(300);
  const [tip, setTip] = useState(false);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(200, Math.floor(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const lo = low ?? high ?? actual;
  const hi = high ?? low ?? actual;
  const min = Math.min(lo, actual);
  const max = Math.max(hi, actual);
  const span = max - min || Math.abs(max) * 0.2 || 1;
  const a = min - span * 0.35;
  const b = max + span * 0.35;
  const x = (v: number) => PAD + ((v - a) / (b - a)) * (width - 2 * PAD);
  const bandL = x(low ?? a);
  const bandR = x(high ?? b);
  const inside = (low == null || actual >= low) && (high == null || actual <= high);

  return (
    <div
      ref={wrap}
      className="chart range-check"
      tabIndex={0}
      role="img"
      aria-label={`${label}: ${fmt(actual, unit)} against a promise of ${low != null ? fmt(low, unit) : "no lower bound"} to ${high != null ? fmt(high, unit) : "no upper bound"}`}
      onFocus={() => setTip(true)}
      onBlur={() => setTip(false)}
      onPointerEnter={() => setTip(true)}
      onPointerLeave={(e) => {
        if (e.pointerType === "mouse") setTip(false);
      }}
      onPointerDown={() => setTip(!tip)}
    >
      <svg width={width} height={H} aria-hidden="true">
        <line className="grid" x1={PAD} x2={width - PAD} y1={24} y2={24} />
        <rect className="band" x={bandL} y={16} width={Math.max(2, bandR - bandL)} height={16} rx={4} />
        <text className="axis" x={bandL} y={11} textAnchor={low == null ? "start" : "middle"}>
          {low != null ? fmt(low, unit) : ""}
        </text>
        <text className="axis" x={bandR} y={11} textAnchor={high == null ? "end" : "middle"}>
          {high != null && high !== low ? fmt(high, unit) : ""}
        </text>
        <circle className={inside ? "dot sel" : "dot miss"} cx={x(actual)} cy={24} r={6} />
        <text className="direct" x={x(actual)} y={H - 1} textAnchor="middle">
          {fmt(actual, unit)}
        </text>
      </svg>
      {tip && (
        <div className="tip" style={{ left: Math.max(0, Math.min(width - 196, x(actual) - 98)), top: H + 2 }} role="status">
          <strong>{fmt(actual, unit)}</strong>
          <span className="tip-sub">{label}</span>
          <span className="tip-sub">{inside ? "Inside the promised range" : "Outside the promised range"}</span>
        </div>
      )}
    </div>
  );
}
