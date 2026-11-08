// Display clean-up for exchange text: NSE prefixes every description with
// "<Company> has informed the Exchange about/regarding".
export function clean(text: string | null | undefined): string {
  if (!text) return "";
  const s = text.replace(/\s+/g, " ").trim();
  const m = s.match(/^.{0,200}?\bhas\s+(?:informed|submitted|intimated)\b(?:\s+to)?(?:\s+the)?(?:\s+exchange)?(?:\s+(?:about|regarding|that))?\s*(.*)$/i);
  const out = (m ? m[1] : s).replace(/^[\s,;:.\-]+/, "").trim();
  return out ? out[0].toUpperCase() + out.slice(1) : s;
}
