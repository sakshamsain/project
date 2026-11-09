import Cite from "./Cite";
import type { AuditorBody, CaseBody, Fact, RisksBody } from "@/lib/dossier";
import { rupee } from "@/lib/text";

function FactLine({ f }: { f: Fact }) {
  return (
    <li>
      {rupee(f.text)}{" "}
      {f.page ? (
        <Cite doc={f.document_id} page={f.page} quote={f.quote ?? undefined} />
      ) : (
        <span className="cite-note">{f.kind === "computed" ? "computed by FINN" : ""}</span>
      )}
    </li>
  );
}

function Side({ title, points, facts, tone }: { title: string; points: CaseBody["bull"]; facts: Map<string, Fact>; tone: string }) {
  return (
    <section className={`side ${tone}`} aria-labelledby={`side-${tone}`}>
      <h2 className="section-title" id={`side-${tone}`}>
        {title}
      </h2>
      {points.length === 0 ? (
        <p className="empty">Nothing in the checked facts supports a point here.</p>
      ) : (
        <ol className="points">
          {points.map((p) => (
            <li key={p.text}>
              <p className="point">{rupee(p.text)}</p>
              <details className="basis">
                <summary>Based on {p.facts.length === 1 ? "1 fact" : `${p.facts.length} facts`}</summary>
                <ul>
                  {p.facts.map((id) => {
                    const f = facts.get(id);
                    return f ? <FactLine key={id} f={f} /> : null;
                  })}
                </ul>
              </details>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export default function Case({ c, auditor, risks }: { c?: CaseBody; auditor?: AuditorBody; risks?: RisksBody }) {
  const facts = new Map((c?.facts ?? []).map((f) => [f.id, f]));
  return (
    <>
      {c ? (
        <div className="case">
          <Side title="The bull case" points={c.bull} facts={facts} tone="bull" />
          <Side title="The bear case" points={c.bear} facts={facts} tone="bear" />
        </div>
      ) : (
        <p className="empty">The case has not been written for this company yet.</p>
      )}
      <p className="section-note" style={{ marginTop: "-0.75rem" }}>
        Each point was written by a model from facts FINN had already checked, and kept only if every figure in it
        appears in the facts it cites. Both sides are shown; FINN does not recommend buying or selling.
      </p>

      {auditor && (auditor.matters.length > 0 || auditor.drawn_attention.length > 0) && (
        <section className="section" aria-labelledby="kam">
          <h2 className="section-title" id="kam">
            What the auditor flagged <span className="n">{auditor.fiscal_year}</span>
          </h2>
          <ul className="said">
            {auditor.drawn_attention.map((d) => (
              <li key={`d${d.page}${d.quote.slice(0, 16)}`}>
                <span className="said-when">{d.kind === "going_concern" ? "Going-concern uncertainty" : "Emphasis of matter"}</span>
                <q>{rupee(d.quote)}</q> <Cite doc={auditor.document_id} page={d.page} quote={d.quote} />
              </li>
            ))}
            {auditor.matters.map((m) => (
              <li key={`m${m.page}${m.quote.slice(0, 16)}`}>
                <span className="said-when">Key audit matter{m.title ? `: ${m.title}` : ""}</span>
                <q>{rupee(m.quote)}</q> <Cite doc={auditor.document_id} page={m.page} quote={m.quote} />
              </li>
            ))}
          </ul>
          <p className="section-note" style={{ marginTop: "0.5rem" }}>
            Key audit matters are the areas the auditor judged most significant; they are not findings against the
            company.
          </p>
        </section>
      )}

      {risks && risks.risks.length > 0 && (
        <section className="section" aria-labelledby="risks">
          <h2 className="section-title" id="risks">
            Risks management names <span className="n">{risks.fiscal_year} MD&amp;A</span>
          </h2>
          <ul className="said">
            {risks.risks.map((r) => (
              <li key={`${r.page}${r.quote.slice(0, 16)}`}>
                {r.title && <span className="said-when">{r.title}</span>}
                <q>{rupee(r.quote)}</q> <Cite doc={risks.document_id} page={r.page} quote={r.quote} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
