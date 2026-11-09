// Display clean-up for exchange text: NSE prefixes every description with
// "<Company> has informed the Exchange about/regarding".
export function clean(text: string | null | undefined): string {
  if (!text) return "";
  const s = text.replace(/\s+/g, " ").trim();
  const m = s.match(/^.{0,200}?\bhas\s+(?:informed|submitted|intimated)\b(?:\s+to)?(?:\s+the)?(?:\s+exchange)?(?:\s+(?:about|regarding|that))?\s*(.*)$/i);
  const out = (m ? m[1] : s).replace(/^[\s,;:.\-]+/, "").trim();
  return out ? out[0].toUpperCase() + out.slice(1) : s;
}

// PDF text often carries the rupee sign as a stray glyph: "C 1,23,745.05 crore",
// "H 361.8 crore". Only a lone C, H or ` directly before an amount in crore or lakh is
// read as ₹; the quote is otherwise shown exactly as it was verified.
export function rupee(text: string): string {
  return text.replace(/(^|[\s(:])[CH`](?=\s?\d[\d,]*(?:\.\d+)?\s*(?:crores?|lakhs?|cr\b))/g, "$1₹");
}

/** Where a verified quote sits in a page's text, matched word by word so that line
 *  breaks, curly quotes and dashes in the PDF text do not matter. */
export function findQuote(text: string, quote: string): [number, number] | null {
  const words = quote.normalize("NFKC").match(/[\p{L}\p{N}]+/gu) ?? [];
  if (words.length < 3) return null;
  const escaped = words.slice(0, 120).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  try {
    const m = new RegExp(escaped.join("[^\\p{L}\\p{N}]+"), "iu").exec(text);
    return m ? [m.index, m.index + m[0].length] : null;
  } catch {
    return null;
  }
}
