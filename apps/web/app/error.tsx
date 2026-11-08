"use client";

import Link from "next/link";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="page">
      <header className="masthead">
        <Link className="wordmark" href="/">
          FINN
        </Link>
      </header>
      <section className="triage">
        <p className="triage-line">This page did not load</p>
        <p className="triage-sub">
          The data service did not answer in time. Your portfolio and settings are safe.
        </p>
      </section>
      <div className="row-form">
        <button type="button" className="button" onClick={() => reset()}>
          Try again
        </button>
        <Link className="button ghost" href="/" style={{ textDecoration: "none" }}>
          Back to today
        </Link>
      </div>
    </main>
  );
}
