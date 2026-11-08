export default function Loading() {
  return (
    <main className="page" aria-busy="true">
      <header className="masthead">
        <span className="wordmark">FINN</span>
      </header>
      <div className="skeleton" style={{ height: "5.5rem", marginTop: "1.5rem" }} />
      <div className="skeleton" style={{ height: "1.4rem", width: "60%", marginTop: "1rem" }} />
      <div className="skeleton" style={{ height: "8rem", marginTop: "1.5rem" }} />
      <div className="skeleton" style={{ height: "8rem", marginTop: "1rem" }} />
      <span className="visually-hidden">Loading</span>
    </main>
  );
}
