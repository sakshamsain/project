"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

type Hit = { symbol: string; name: string; isin: string };

export default function CompanySearch() {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    input.current?.focus();
  }, []);

  useEffect(() => {
    const term = q.trim();
    if (!term) {
      setHits([]);
      return;
    }
    const ctrl = new AbortController();
    const t = setTimeout(async () => {
      setBusy(true);
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(term)}`, { signal: ctrl.signal });
        if (res.ok) setHits(((await res.json()) as { results: Hit[] }).results);
      } catch {
        // a newer keystroke cancelled this one
      } finally {
        setBusy(false);
      }
    }, 180);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [q]);

  return (
    <section className="section" style={{ marginTop: "1.25rem" }}>
      <label className="visually-hidden" htmlFor="company-q">
        Company name or NSE symbol
      </label>
      <input
        ref={input}
        id="company-q"
        type="search"
        placeholder="Company name or NSE symbol"
        autoComplete="off"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <ul className="lines" style={{ marginTop: "0.75rem" }} aria-live="polite" aria-busy={busy}>
        {q.trim() && !busy && hits.length === 0 && <li className="empty">No listed company matches “{q.trim()}”.</li>}
        {hits.map((h) => (
          <li className="line" key={h.isin}>
            <Link className="stamp" href={`/company/${encodeURIComponent(h.symbol)}`}>
              {h.symbol}
            </Link>
            <div className="line-text">
              <Link href={`/company/${encodeURIComponent(h.symbol)}`}>{h.name}</Link>
              <span className="line-kind">
                <Link href={`/research/${encodeURIComponent(h.symbol)}`}>Promise ledger</Link>
              </span>
            </div>
          </li>
        ))}
      </ul>
      {!q.trim() && (
        <p className="section-note">
          Every company listed on NSE: open its filings, prices and results, add it to your
          portfolio, or build its promise ledger.
        </p>
      )}
    </section>
  );
}
