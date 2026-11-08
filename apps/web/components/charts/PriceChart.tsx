"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { fmtDay, fmtPrice } from "@/lib/format";
import { axisLabel, niceTicks, signedPct, volumeLabel } from "./scale";

export type PriceBar = { d: string; close: number; volume: number };
export type ChartEvent = {
  d: string;
  id: string;
  headline: string;
  tier: "front" | "oneliner";
  label: string;
};

const RANGES = [
  { key: "1M", n: 21, words: "1 month" },
  { key: "3M", n: 63, words: "3 months" },
  { key: "6M", n: 126, words: "6 months" },
  { key: "1Y", n: 250, words: "1 year" },
] as const;

const H = 196; // price plot height
const VH = 44; // volume plot height
const PAD_T = 10;
const PAD_B = 6;
const AXIS_W = 56; // y labels on the right

export default function PriceChart({ symbol, bars, events }: { symbol: string; bars: PriceBar[]; events: ChartEvent[] }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(360);
  const ranges = RANGES.filter((r, i) => i === 0 || bars.length >= Math.min(r.n, RANGES[i - 1].n + 5));
  const [range, setRange] = useState<string>(ranges.find((r) => r.key === "3M")?.key ?? ranges[ranges.length - 1].key);
  const [idx, setIdx] = useState<number | null>(null);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(260, Math.floor(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const n = RANGES.find((r) => r.key === range)?.n ?? 63;
  const view = useMemo(() => bars.slice(-n), [bars, n]);
  const words = RANGES.find((r) => r.key === range)?.words ?? "";

  const plotW = width - AXIS_W;
  const step = plotW / Math.max(1, view.length - 1);
  const x = (i: number) => i * step;
  const closes = view.map((b) => b.close);
  const ticks = niceTicks(Math.min(...closes), Math.max(...closes), 4);
  const yMin = ticks[0];
  const yMax = ticks[ticks.length - 1];
  const y = (v: number) => PAD_T + (1 - (v - yMin) / (yMax - yMin || 1)) * (H - PAD_T - PAD_B);
  const vMax = Math.max(1, ...view.map((b) => b.volume));
  const barW = Math.max(1, Math.min(24, step * 0.6));

  const line = view.map((b, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(b.close).toFixed(1)}`).join("");
  const area = view.length ? `${line}L${x(view.length - 1)},${H - PAD_B}L0,${H - PAD_B}Z` : "";

  // Each filing sits on the first session on or after the day it was filed.
  const marks = useMemo(() => {
    const out = new Map<number, ChartEvent[]>();
    for (const e of events) {
      const i = view.findIndex((b) => b.d >= e.d);
      if (i >= 0) out.set(i, [...(out.get(i) ?? []), e]);
    }
    return out;
  }, [events, view]);

  if (view.length < 2) return <p className="empty">Not enough price history yet.</p>;

  const first = view[0];
  const last = view[view.length - 1];
  const change = (last.close / first.close - 1) * 100;
  const sel = idx == null ? null : Math.min(idx, view.length - 1);
  const selBar = sel == null ? null : view[sel];
  const selPrev = sel != null && sel > 0 ? view[sel - 1] : null;
  const selEvents = sel == null ? [] : (marks.get(sel) ?? []);

  function pick(clientX: number) {
    const el = wrap.current;
    if (!el) return;
    const px = clientX - el.getBoundingClientRect().left;
    setIdx(Math.max(0, Math.min(view.length - 1, Math.round(px / step))));
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      const cur = sel ?? view.length - 1;
      setIdx(Math.max(0, Math.min(view.length - 1, cur + (e.key === "ArrowLeft" ? -1 : 1))));
    } else if (e.key === "Home") setIdx(0);
    else if (e.key === "End") setIdx(view.length - 1);
    else if (e.key === "Escape") setIdx(null);
  }

  const tipLeft = sel == null ? 0 : Math.max(0, Math.min(width - 196, x(sel) - 98));

  return (
    <figure className="chart">
      <div className="chart-head">
        <figcaption>
          <span className={change < 0 ? "down" : "up"}>
            {change < 0 ? "▼" : "▲"} {signedPct(change)}
          </span>{" "}
          over {words}, closing {fmtPrice(last.close)} on {fmtDay(last.d)}
        </figcaption>
        <div className="seg" role="group" aria-label="Time range">
          {ranges.map((r) => (
            <button
              key={r.key}
              type="button"
              aria-pressed={r.key === range}
              onClick={() => {
                setRange(r.key);
                setIdx(null);
              }}
            >
              {r.key}
            </button>
          ))}
        </div>
      </div>

      <div
        ref={wrap}
        className="chart-plot"
        tabIndex={0}
        role="group"
        aria-label={`${symbol} closing prices over ${words}. Use the left and right arrow keys to read each day.`}
        onKeyDown={onKey}
        onPointerMove={(e) => pick(e.clientX)}
        onPointerDown={(e) => pick(e.clientX)}
        onPointerLeave={(e) => {
          if (e.pointerType === "mouse") setIdx(null);
        }}
      >
        <svg width={width} height={H + VH + 8} role="img" aria-hidden="true">
          {ticks.map((t) => (
            <g key={t}>
              <line className="grid" x1={0} x2={plotW} y1={y(t)} y2={y(t)} />
              <text className="axis" x={plotW + 6} y={y(t) + 4}>
                {axisLabel(t, yMax)}
              </text>
            </g>
          ))}
          <path className="area" d={area} />
          <path className="line" d={line} />
          {[...marks.entries()].map(([i, evs]) => {
            const front = evs.some((e) => e.tier === "front");
            return (
              <g key={i} className="marker">
                <circle cx={x(i)} cy={y(view[i].close)} r={12} className="hit" />
                <circle cx={x(i)} cy={y(view[i].close)} r={4.5} className={front ? "dot front" : "dot"} />
              </g>
            );
          })}
          {view.map((b, i) => (
            <rect
              key={b.d}
              className={sel === i ? "vol on" : "vol"}
              x={x(i) - barW / 2}
              y={H + 8 + VH - Math.max(1, (b.volume / vMax) * (VH - 2))}
              width={barW}
              height={Math.max(1, (b.volume / vMax) * (VH - 2))}
            />
          ))}
          <line className="grid" x1={0} x2={plotW} y1={H + 8 + VH} y2={H + 8 + VH} />
          <text className="axis" x={plotW + 6} y={H + 8 + 12}>
            Volume
          </text>
          {selBar && sel != null && (
            <g>
              <line className="cross" x1={x(sel)} x2={x(sel)} y1={PAD_T - 4} y2={H + 8 + VH} />
              <circle className="dot sel" cx={x(sel)} cy={y(selBar.close)} r={4.5} />
            </g>
          )}
        </svg>

        {selBar && sel != null && (
          <div className="tip" style={{ left: tipLeft }} role="status">
            <strong>{fmtPrice(selBar.close)}</strong>
            {selPrev && (
              <span className={selBar.close < selPrev.close ? "down" : "up"}>
                {" "}
                {signedPct((selBar.close / selPrev.close - 1) * 100)}
              </span>
            )}
            <span className="tip-sub">
              {fmtDay(selBar.d)}, volume {volumeLabel(selBar.volume)}
            </span>
            {selEvents.slice(0, 2).map((e) => (
              <Link key={e.id} href={`/event/${e.id}`} className="tip-event">
                {e.label}: {e.headline}
              </Link>
            ))}
          </div>
        )}
      </div>

      <p className="chart-legend">
        <span className="key dot-key front" aria-hidden="true" /> filing on the front page{" "}
        <span className="key dot-key" aria-hidden="true" /> other notable filing. Tap a day to read it.
      </p>

      <details className="chart-table">
        <summary>Show as a table</summary>
        <table>
          <thead>
            <tr>
              <th scope="col">Day</th>
              <th scope="col">Close</th>
              <th scope="col">Change</th>
              <th scope="col">Volume</th>
            </tr>
          </thead>
          <tbody>
            {view
              .map((b, i) => ({ b, prev: i > 0 ? view[i - 1] : null }))
              .reverse()
              .map(({ b, prev }) => (
                <tr key={b.d}>
                  <td>{fmtDay(b.d)}</td>
                  <td>{fmtPrice(b.close)}</td>
                  <td>{prev ? signedPct((b.close / prev.close - 1) * 100) : ""}</td>
                  <td>{volumeLabel(b.volume)}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
