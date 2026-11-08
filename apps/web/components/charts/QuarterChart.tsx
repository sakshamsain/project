"use client";

import { useEffect, useRef, useState } from "react";
import { barPath, niceTicks, signedPct } from "./scale";

export type QuarterPoint = { label: string; fy: number; q: number; value: number };

const H = 132;
const PAD_T = 18; // room for the direct label on the latest bar
const PAD_B = 22; // quarter labels
const AXIS_W = 64;

function crore(v: number): string {
  return `₹${v.toLocaleString("en-IN", { maximumFractionDigits: Math.abs(v) >= 100 ? 0 : 1 })} Cr`;
}

/** The quarter n steps before (fy, q). */
function back(fy: number, q: number, n: number): [number, number] {
  const idx = fy * 4 + (q - 1) - n;
  return [Math.floor(idx / 4), (idx % 4) + 1];
}

export default function QuarterChart({ title, points }: { title: string; points: QuarterPoint[] }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(340);
  const [sel, setSel] = useState<number | null>(null);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(240, Math.floor(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  if (points.length === 0) return null;
  const byKey = new Map(points.map((p) => [`${p.fy}-${p.q}`, p]));
  const change = (p: QuarterPoint, n: number) => {
    const [fy, q] = back(p.fy, p.q, n);
    const prev = byKey.get(`${fy}-${q}`);
    return prev && prev.value !== 0 ? ((p.value - prev.value) / Math.abs(prev.value)) * 100 : null;
  };

  const plotW = width - AXIS_W;
  const band = plotW / points.length;
  const barW = Math.min(24, band * 0.55);
  const vals = points.map((p) => p.value);
  const ticks = niceTicks(Math.min(0, ...vals), Math.max(0, ...vals), 3);
  const lo = ticks[0];
  const hi = ticks[ticks.length - 1];
  const y = (v: number) => PAD_T + (1 - (v - lo) / (hi - lo || 1)) * (H - PAD_T - PAD_B);
  const cx = (i: number) => band * i + band / 2;
  const showEvery = band < 44 ? 2 : 1;
  const last = points.length - 1;
  const s = sel == null ? null : points[sel];

  return (
    <figure className="chart qchart">
      <figcaption className="qchart-title">{title}, &#8377; crore</figcaption>
      <div
        ref={wrap}
        className="chart-plot"
        tabIndex={0}
        role="group"
        aria-label={`${title} by quarter. Use the left and right arrow keys to read each quarter.`}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
            e.preventDefault();
            const cur = sel ?? last;
            setSel(Math.max(0, Math.min(last, cur + (e.key === "ArrowLeft" ? -1 : 1))));
          } else if (e.key === "Escape") setSel(null);
        }}
        onPointerLeave={(e) => {
          if (e.pointerType === "mouse") setSel(null);
        }}
      >
        <svg width={width} height={H} aria-hidden="true">
          {ticks.map((t) => (
            <g key={t}>
              <line className={t === 0 ? "baseline" : "grid"} x1={0} x2={plotW} y1={y(t)} y2={y(t)} />
              <text className="axis" x={plotW + 6} y={y(t) + 4}>
                {t.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
              </text>
            </g>
          ))}
          {points.map((p, i) => (
            <g key={p.label}>
              <path className={sel === i ? "bar on" : "bar"} d={barPath(cx(i) - barW / 2, barW, y(0), y(p.value))} />
              <rect
                className="hit"
                x={band * i}
                y={0}
                width={band}
                height={H}
                onPointerEnter={() => setSel(i)}
                onPointerDown={() => setSel(i)}
              />
              {(i % showEvery === (last % showEvery) || i === last) && (
                <text className="axis xlabel" x={cx(i)} y={H - 6} textAnchor="middle">
                  {p.label}
                </text>
              )}
            </g>
          ))}
          <text
            className="direct"
            x={cx(last)}
            y={points[last].value >= 0 ? y(points[last].value) - 5 : y(points[last].value) + 13}
            textAnchor="middle"
          >
            {points[last].value.toLocaleString("en-IN", { maximumFractionDigits: Math.abs(points[last].value) >= 100 ? 0 : 1 })}
          </text>
        </svg>
        {s && sel != null && (
          <div className="tip" style={{ left: Math.max(0, Math.min(width - 176, cx(sel) - 88)) }} role="status">
            <strong>{crore(s.value)}</strong>
            <span className="tip-sub">{s.label}</span>
            <span className="tip-sub">
              {change(s, 1) != null ? `${signedPct(change(s, 1)!)} QoQ` : "QoQ n/a"}
              {", "}
              {change(s, 4) != null ? `${signedPct(change(s, 4)!)} YoY` : "YoY n/a"}
            </span>
          </div>
        )}
      </div>
    </figure>
  );
}
