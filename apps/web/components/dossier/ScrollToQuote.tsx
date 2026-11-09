"use client";

import { useEffect } from "react";

/** Brings the marked quote into view when a citation opens its page. */
export default function ScrollToQuote() {
  useEffect(() => {
    const el = document.getElementById("quote");
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
  }, []);
  return null;
}
