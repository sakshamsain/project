"use client";

import { useEffect } from "react";

/** Scrolls the section strip so the open tab is in view on a narrow screen. */
export default function ActiveTab({ tab }: { tab: string }) {
  useEffect(() => {
    const el = document.querySelector<HTMLElement>('.dtabs a[aria-current="page"]');
    const strip = el?.closest("ul");
    if (!el || !strip) return;
    strip.scrollLeft = Math.max(0, el.offsetLeft - (strip.clientWidth - el.offsetWidth) / 2);
  }, [tab]);
  return null;
}
