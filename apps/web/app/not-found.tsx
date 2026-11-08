import Link from "next/link";

export default function NotFound() {
  return (
    <main className="page">
      <header className="masthead">
        <Link className="wordmark" href="/">
          FINN
        </Link>
      </header>
      <section className="triage">
        <p className="triage-line">Not here</p>
        <p className="triage-sub">
          That company or filing is not in FINN. <Link href="/">Back to today</Link>.
        </p>
      </section>
    </main>
  );
}
