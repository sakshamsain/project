"use client";

import { useEffect } from "react";

export const PREV_VISIT = "finn_prev_visit";
const THIS_VISIT = "finn_visit";
const GAP_MS = 30 * 60_000;

function read(name: string): number | null {
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=(\\d+)`));
  return m ? Number(m[1]) : null;
}

function write(name: string, value: number) {
  document.cookie = `${name}=${value}; path=/; max-age=${60 * 60 * 24 * 90}; samesite=lax`;
}

/** Remembers visits on this device: a visit begins after 30 minutes away, and the start
 *  of the one before becomes "since last visit" on the Brief. */
export default function LastVisit() {
  useEffect(() => {
    const now = Date.now();
    const current = read(THIS_VISIT);
    if (current === null || now - current > GAP_MS) {
      if (current !== null) write(PREV_VISIT, current);
      write(THIS_VISIT, now);
    } else {
      write(THIS_VISIT, now); // still the same visit: keep it alive
    }
  }, []);
  return null;
}
