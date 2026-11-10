"use client";

import { useEffect } from "react";

/**
 * Scrolls the section strip so the open tab is in view on a narrow screen, and marks
 * which edges have more tabs behind them so only those edges fade.
 */
export default function ActiveTab({ tab }: { tab: string }) {
  useEffect(() => {
    const el = document.querySelector<HTMLElement>('.dtabs a[aria-current="page"]');
    const strip = el?.closest("ul");
    if (!el || !strip) return;
    const mark = () => {
      const max = strip.scrollWidth - strip.clientWidth;
      strip.dataset.more =
        max <= 1 ? "none" : strip.scrollLeft <= 1 ? "end" : strip.scrollLeft >= max - 1 ? "start" : "both";
    };
    strip.scrollLeft = Math.max(0, el.offsetLeft - (strip.clientWidth - el.offsetWidth) / 2);
    mark();
    strip.addEventListener("scroll", mark, { passive: true });
    window.addEventListener("resize", mark);
    return () => {
      strip.removeEventListener("scroll", mark);
      window.removeEventListener("resize", mark);
    };
  }, [tab]);
  return null;
}
