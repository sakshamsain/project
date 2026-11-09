import Link from "next/link";

/** A citation chip: "p. 295" opens FINN's copy of that page with the quote marked, or
 *  the original PDF at the page when FINN did not keep the page. */
export default function Cite({
  doc,
  page,
  quote,
  url,
  label,
}: {
  doc?: number | string | null;
  page?: number | null;
  quote?: string | null;
  url?: string | null;
  label?: string;
}) {
  if (!page) return null;
  const text = label ?? `p. ${page}`;
  if (doc) {
    const q = quote ? `?q=${encodeURIComponent(quote.slice(0, 700))}` : "";
    return (
      <Link className="cite" href={`/source/${doc}/${page}${q}`} aria-label={`Source, page ${page}`}>
        {text}
      </Link>
    );
  }
  if (url) {
    return (
      <a className="cite" href={`${url}#page=${page}`} target="_blank" rel="noopener noreferrer">
        {text}
      </a>
    );
  }
  return null;
}
