import Link from "next/link";
import { notFound } from "next/navigation";
import Masthead from "@/components/Masthead";
import ScrollToQuote from "@/components/dossier/ScrollToQuote";
import { getSourcePage } from "@/lib/dossier";
import { sessionUser } from "@/lib/profile";
import { findQuote } from "@/lib/text";

export const dynamic = "force-dynamic";

const KIND: Record<string, string> = {
  annual_report: "Annual report",
  transcript: "Earnings-call transcript",
  results: "Results",
  presentation: "Investor presentation",
};

export default async function SourcePage({
  params,
  searchParams,
}: {
  params: Promise<{ doc: string; page: string }>;
  searchParams: Promise<{ q?: string }>;
}) {
  const { doc, page } = await params;
  const { q } = await searchParams;
  if (!/^\d{1,12}$/.test(doc) || !/^\d{1,4}$/.test(page)) notFound();
  const [p, user] = await Promise.all([getSourcePage(doc, Number(page)), sessionUser()]);
  if (!p) notFound();
  // The PDF's own line breaks only fit its page width: join them, keep paragraph breaks.
  const text = p.text ? p.text.normalize("NFKC").replace(/([^\n])\n(?=[^\n])/g, "$1 ") : null;
  const hit = text && q ? findQuote(text, q.slice(0, 700)) : null;
  const pdf = p.source_url ? `${p.source_url}#page=${p.page_no}` : null;
  return (
    <main className="page">
      <Masthead user={user} note="Source" />
      {p.symbol && (
        <p className="back">
          <Link href={`/research/${encodeURIComponent(p.symbol)}`}>← {p.company}</Link>
        </p>
      )}
      <section className="triage" aria-label="Document">
        <h1 className="source-title">
          {KIND[p.doc_type] ?? "Filing"}
          {p.period ? `, ${p.period.replace(/^(Q\d)(FY\d+)$/, "$1 $2")}` : ""}
        </h1>
        <p className="triage-sub">
          {p.company}. Page {p.page_no}
          {p.pages ? ` of ${p.pages}` : ""} of the PDF filed with NSE.
        </p>
        {pdf && (
          <a className="button small" href={pdf} target="_blank" rel="noopener noreferrer">
            Open the PDF at page {p.page_no}
          </a>
        )}
      </section>
      {text ? (
        <>
          {q && !hit && (
            <p className="section-note">
              FINN found the quote on this page when it checked it; the PDF&apos;s text breaks it differently here, so it
              is not marked.
            </p>
          )}
          <div className="source-page panel" lang="en">
            {hit ? (
              <>
                {text.slice(0, hit[0])}
                <mark id="quote">{text.slice(hit[0], hit[1])}</mark>
                {text.slice(hit[1])}
              </>
            ) : (
              text
            )}
          </div>
          {hit && <ScrollToQuote />}
          <p className="section-note" style={{ marginTop: "0.75rem" }}>
            The page&apos;s text as FINN read it from the PDF, reflowed to fit the screen; the PDF is the record.
          </p>
        </>
      ) : (
        <p className="empty">
          FINN keeps only the pages it reads from a report, and this is not one of them. The PDF has every page.
        </p>
      )}
    </main>
  );
}
