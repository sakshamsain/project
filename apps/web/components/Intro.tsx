"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const KEY = "finn_intro_seen";

export default function Intro() {
  const [show, setShow] = useState(false);
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
    <aside className="panel intro" aria-label="How FINN works">
      <p className="building-title">How FINN works</p>
      <ul>
        <li>Every filing your companies make on NSE, ranked: read first, in brief, or routine.</li>
        <li>After the close, Pulse flags unusual moves and the filing behind each one.</li>
        <li>Research checks what management promised on calls against what it reported.</li>
      </ul>
      <div className="row-form">
        <button type="button" className="button small" onClick={dismiss}>
          Got it
        </button>
        <Link className="button ghost small" href="/settings" onClick={dismiss} style={{ textDecoration: "none" }}>
          Use my own portfolio
        </Link>
      </div>
    </aside>
  );
}
