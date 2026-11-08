export type PeopleQuote = { text: string; page: number };

export type PeoplePerson = {
  name: string;
  role: string;
  change: string;
  effective: string | null;
  background: PeopleQuote[];
  reason: PeopleQuote | null;
  linkedin_search: string | null;
  source?: string | null;
};

export type PeopleCardData = {
  status: "ok" | "empty" | "scanned" | "error";
  people?: PeoplePerson[];
  sources?: (string | null)[];
};

const CHANGE: Record<string, string> = {
  appointed: "Appointed",
  reappointed: "Reappointed",
  redesignated: "Redesignated",
  resigned: "Resigned",
  ceased: "Ceased",
  retired: "Retired",
  other: "Changed",
};

function Cite({ q, source }: { q: PeopleQuote; source: string | null | undefined }) {
  return (
    <li>
      <q>{q.text}</q>{" "}
      {source ? (
        <a href={`${source}#page=${q.page}`} target="_blank" rel="noopener noreferrer" className="cite">
          p.&nbsp;{q.page}
        </a>
      ) : (
        <span className="cite">p.&nbsp;{q.page}</span>
      )}
    </li>
  );
}

export default function PeopleCard({ card, compact = false }: { card: PeopleCardData; compact?: boolean }) {
  if (card.status !== "ok" || !card.people?.length) return null;
  const fallbackSource = card.sources?.find(Boolean) ?? null;
  const people = compact ? card.people.slice(0, 2) : card.people;
  return (
    <section className="people" aria-label="Who is changing">
      {people.map((p) => {
        const source = p.source ?? fallbackSource;
        const quotes = compact ? p.background.slice(0, 2) : p.background;
        return (
          <div className="person" key={p.name}>
            <p className="person-head">
              <span className="person-change">{CHANGE[p.change] ?? "Changed"}</span> {p.name}
              <span className="person-role">
                {p.role}
                {p.effective ? `, from ${p.effective}` : ""}
              </span>
            </p>
            {quotes.length > 0 && (
              <ul className="quotes">
                {quotes.map((q) => (
                  <Cite key={q.text} q={q} source={source} />
                ))}
              </ul>
            )}
            {p.reason && (
              <ul className="quotes">
                <Cite q={p.reason} source={source} />
              </ul>
            )}
            {!compact && p.linkedin_search && (p.change === "appointed" || p.change === "redesignated") && (
              <a className="person-link" href={p.linkedin_search} target="_blank" rel="noopener noreferrer">
                Search LinkedIn for {p.name}
              </a>
            )}
          </div>
        );
      })}
      {compact && card.people.length > 2 && (
        <p className="results-note fine">and {card.people.length - 2} more on the event page</p>
      )}
      <p className="results-note fine">
        Quoted from the company&apos;s filing; each quote was checked against the PDF text.
      </p>
    </section>
  );
}
