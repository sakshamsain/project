"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const KEY = "finn_intro_seen";

/** A first-visit explainer, folded to one line so the brief stays on the first screen. */
export default function Intro() {
  const [show, setShow] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    try {
      setShow(window.localStorage.getItem(KEY) !== "1");
    } catch {
      setShow(true);
    }
  }, []);
  if (!show) return null;
  function dismiss() {
    try {
      window.localStorage.setItem(KEY, "1");
    } catch {
      // private mode: the card simply comes back next time
    }
    setShow(false);
  }
  return (
    <details className="panel intro" open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>New here? How FINN works</summary>
      <ol>
        <li>Today ranks every filing your companies make on NSE: read first, in brief, or routine.</li>
        <li>After the close, Pulse flags unusual moves and the filing behind each one.</li>
        <li>Research checks what management promised on calls against what the company then filed.</li>
      </ol>
      <div className="row-form">
        <button type="button" className="button small" onClick={dismiss}>
          Got it
        </button>
        <Link className="button ghost small" href="/settings" onClick={dismiss}>
          Use my own portfolio
        </Link>
      </div>
    </details>
  );
}
