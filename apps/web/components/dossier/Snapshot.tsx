import Link from "next/link";
import Cite from "./Cite";
import type { AuditorBody, BusinessBody, CashBody } from "@/lib/dossier";
import { fmtCrore, fmtPct, fmtShare } from "@/lib/format";
import type { LedgerStatus } from "@/lib/research";
import { rupee } from "@/lib/text";

const OPINION: Record<string, string> = {
  unmodified: "an unmodified (clean) opinion",
  qualified: "a qualified opinion",
  adverse: "an adverse opinion",
  disclaimer: "a disclaimer of opinion",
};

export default function Snapshot({
  symbol,
  business,
  cash,
  auditor,
  counts,
  promises,
}: {
  symbol: string;
  business?: BusinessBody;
  cash?: CashBody;
  auditor?: AuditorBody;
  counts: Partial<Record<LedgerStatus, number>>;
  promises: number;
}) {
  const year = cash?.years.find((y) => y.failures.length === 0);
  const doc = business?.document_id ?? null;
  const measured = (counts.delivered ?? 0) + (counts.missed ?? 0) + (counts.on_track ?? 0) + (counts.off_track ?? 0);
  const shares = business?.activities.filter((a) => a.share != null) ?? [];
  return (
    <>
      {business && (business.description || business.activities.length > 0) && (
        <section className="section" aria-labelledby="does">
          <h2 className="section-title" id="does">
            What it does
          </h2>
          {business.description && (
            <p className="lede">
              <q>{rupee(business.description.quote)}</q>{" "}
              <Cite doc={doc} page={business.description.page} quote={business.description.quote} />
            </p>
          )}
          {shares.length > 0 ? (
            <ul className="shares">
              {shares.map((a) => (
                <li key={a.name}>
                  <span className="share-bar" style={{ width: `${Math.min(100, a.share ?? 0)}%` }} aria-hidden="true" />
                  <span className="share-text">
                    <strong>{fmtShare(a.share ?? 0)}</strong> of turnover: {a.name} <Cite doc={doc} page={a.page} quote={a.name} />
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            business.activities.length > 0 && (
              <p className="section-note">
                Activities: {business.activities.map((a) => a.name).join("; ")}.{" "}
                <Cite doc={doc} page={business.activities[0].page} quote={business.activities[0].name} />
              </p>
            )
          )}
          <dl className="kv">
            {business.exports && (
              <>
                <dt>Exports, share of turnover</dt>
                <dd>
                  {fmtShare(business.exports.value)} <Cite doc={doc} page={business.exports.page} />
                </dd>
              </>
            )}
            {business.countries && (
              <>
                <dt>Countries served</dt>
                <dd>
                  {business.countries.value} <Cite doc={doc} page={business.countries.page} />
                </dd>
              </>
            )}
            {business.states && (
              <>
                <dt>Indian states served</dt>
                <dd>
                  {business.states.value} <Cite doc={doc} page={business.states.page} />
                </dd>
              </>
            )}
          </dl>
          <p className="section-note" style={{ marginTop: "0.6rem" }}>
            From the {business.fiscal_year} Business Responsibility and Sustainability Report
            {business.boundary ? `, prepared on a ${business.boundary} basis` : ""}.
          </p>
        </section>
      )}

      {year && (
        <section className="section" aria-labelledby="figures">
          <h2 className="section-title" id="figures">
            {year.fiscal_year} in figures <span className="n">₹ crore</span>
          </h2>
          <dl className="kv">
            {year.revenue != null && (
              <>
                <dt>{cash?.lender ? "Total revenue from operations" : "Revenue from operations"}</dt>
                <dd>
                  {fmtCrore(year.revenue)}
                  {year.revenue_growth_pct != null && <span className="kv-sub"> {fmtPct(year.revenue_growth_pct)}</span>}{" "}
                  <Cite doc={year.document_id} page={year.pages.revenue} />
                </dd>
              </>
            )}
            {year.pat != null && (
              <>
                <dt>Profit for the year</dt>
                <dd>
                  {fmtCrore(year.pat)}
                  {year.pat_growth_pct != null && <span className="kv-sub"> {fmtPct(year.pat_growth_pct)}</span>}{" "}
                  <Cite doc={year.document_id} page={year.pages.pat ?? year.pages.pat_owners} />
                </dd>
              </>
            )}
            {year.cfo != null && (
              <>
                <dt>Operating cash flow</dt>
                <dd>
                  {fmtCrore(year.cfo)} <Cite doc={year.document_id} page={year.pages.cfo} />
                </dd>
              </>
            )}
            {year.fcf != null && (
              <>
                <dt>Free cash flow</dt>
                <dd>{fmtCrore(year.fcf)}</dd>
              </>
            )}
          </dl>
          <p className="section-note" style={{ marginTop: "0.6rem" }}>
            {year.quarters.status === "matches"
              ? "Revenue and profit match the sum of the four quarterly filings. "
              : ""}
            Change on the year before in grey. <Link href={`/research/${symbol}?tab=cash`}>Cash in detail</Link>
          </p>
        </section>
      )}

      <section className="section" aria-labelledby="kept">
        <h2 className="section-title" id="kept">
          Promises
        </h2>
        <p className="lede-small">
          {promises === 0
            ? "No forward guidance found in the last four earnings calls."
            : `${promises} promises in the last four earnings calls; ${measured} can be checked against filed figures`}
          {measured > 0 && (
            <>
              {": "}
              {[
                ["delivered", "delivered"],
                ["on_track", "on track"],
                ["off_track", "off track"],
                ["missed", "missed"],
              ]
                .filter(([k]) => (counts[k as LedgerStatus] ?? 0) > 0)
                .map(([k, label]) => `${counts[k as LedgerStatus]} ${label}`)
                .join(", ")}
            </>
          )}
          .{" "}
          {promises > 0 && <Link href={`/research/${symbol}?tab=promises`}>See the ledger</Link>}
        </p>
      </section>

      {auditor?.kind && (
        <section className="section" aria-labelledby="audit">
          <h2 className="section-title" id="audit">
            Auditor
          </h2>
          <p className="lede-small">
            {auditor.firm ?? "The auditor"} gave {OPINION[auditor.kind]} on the {auditor.fiscal_year}{" "}
            {cash?.basis ?? ""} financial statements.{" "}
            <Cite doc={auditor.document_id} page={auditor.page} />
          </p>
          {auditor.drawn_attention.map((d) => (
            <p className="notice" key={d.page + d.quote.slice(0, 20)}>
              {d.kind === "going_concern" ? "Going-concern uncertainty: " : "The auditor draws attention to: "}
              <q>{rupee(d.quote)}</q> <Cite doc={auditor.document_id} page={d.page} quote={d.quote} />
            </p>
          ))}
          {auditor.matters.length > 0 && (
            <p className="section-note">
              Key audit matters: {auditor.matters.map((m) => m.title || "unnamed").join("; ")}.{" "}
              <Link href={`/research/${symbol}?tab=case`}>Read them</Link>
            </p>
          )}
        </section>
      )}
    </>
  );
}
