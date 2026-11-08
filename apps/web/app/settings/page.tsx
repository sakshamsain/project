import Link from "next/link";
import Masthead from "@/components/Masthead";
import PushToggle from "@/components/PushToggle";
import SignOut from "@/components/SignOut";
import { fmtPct, fmtPrice } from "@/lib/format";
import { currentProfile } from "@/lib/profile";
import { FLOORS, getHoldings, getThresholds, searchCompanies } from "@/lib/queries";
import { addHolding, removeHolding, resetToDemo, updateThresholds } from "./actions";

export const dynamic = "force-dynamic";
export const metadata = { title: "Settings" };

export default async function Settings({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; saved?: string }>;
}) {
  const { q, saved } = await searchParams;
  const profile = await currentProfile();
  const [holdings, matches, t] = await Promise.all([
    getHoldings(profile.id),
    q ? searchCompanies(q) : Promise.resolve([]),
    getThresholds(profile.id),
  ]);
  const held = new Set(holdings.map((h) => h.isin));
  return (
    <main className="page">
      <Masthead user={profile.user} note="Settings" />

      <section className="section" id="account" aria-labelledby="account-title" style={{ marginTop: "1.5rem" }}>
        <h2 className="section-title" id="account-title">
          Account
        </h2>
        {profile.user ? (
          <div className="panel account-row">
            <div>
              <strong>{profile.user.name}</strong>
              <span className="line-kind">
                {profile.user.email}. Your portfolio, alert limits and notifications follow this account.
              </span>
            </div>
            <SignOut />
          </div>
        ) : (
          <div className="panel">
            <p className="section-note" style={{ margin: "0 0 0.75rem" }}>
              Sign in to keep your portfolio, alert limits and notifications on every device. You can
              use FINN without an account; this device then keeps its own portfolio.
            </p>
            <div className="row-form">
              <Link className="button small" href="/signin?mode=signup" style={{ textDecoration: "none" }}>
                Create account
              </Link>
              <Link className="button ghost small" href="/signin" style={{ textDecoration: "none" }}>
                Sign in
              </Link>
            </div>
          </div>
        )}
      </section>

      <section className="section" aria-labelledby="portfolio">
        <h2 className="section-title" id="portfolio">
          Your portfolio <span className="n">{holdings.length}</span>
        </h2>
        {profile.isDemo && (
          <p className="notice">
            You are looking at the demo portfolio. Add or remove a company and this device gets
            its own copy; sign in to keep it on every device.
          </p>
        )}
        <form method="get" action="/settings" className="row-form" role="search" style={{ marginBottom: "0.75rem" }}>
          <label className="visually-hidden" htmlFor="q">
            Find a company by name or NSE symbol
          </label>
          <input id="q" name="q" type="search" placeholder="Name or NSE symbol" defaultValue={q ?? ""} autoComplete="off" />
          <button className="button" type="submit">
            Find
          </button>
        </form>
        {q && (
          <ul className="holdings" aria-label="Search results" style={{ marginBottom: "1.25rem" }}>
            {matches.length === 0 && <li className="empty">No listed company matches {q}.</li>}
            {matches.map((m) => (
              <li key={m.isin}>
                <span>
                  <span className="stamp quiet">{m.symbol}</span>
                  <span className="name">{m.name}</span>
                </span>
                {held.has(m.isin) ? (
                  <span className="name">In portfolio</span>
                ) : (
                  <form action={addHolding}>
                    <input type="hidden" name="isin" value={m.isin} />
                    <input type="hidden" name="back" value={`/settings?q=${encodeURIComponent(q)}`} />
                    <button className="button small" type="submit">
                      Add
                    </button>
                  </form>
                )}
              </li>
            ))}
          </ul>
        )}
        <ul className="holdings">
          {holdings.map((h) => (
            <li key={h.isin}>
              <span>
                <Link className="stamp" href={`/company/${encodeURIComponent(h.symbol)}`}>
                  {h.symbol}
                </Link>
                <span className="name">
                  {h.close != null ? fmtPrice(h.close) : h.name}
                  {h.return_pct != null && (
                    <span className={h.return_pct < 0 ? "down" : "up"}> {fmtPct(h.return_pct)}</span>
                  )}
                </span>
              </span>
              <form action={removeHolding}>
                <input type="hidden" name="isin" value={h.isin} />
                <button className="button ghost small" type="submit" aria-label={`Remove ${h.symbol}`}>
                  Remove
                </button>
              </form>
            </li>
          ))}
        </ul>
        {!profile.isDemo && (
          <form action={resetToDemo} style={{ marginTop: "0.75rem" }}>
            <button className="button ghost small" type="submit">
              Reset to the demo portfolio
            </button>
          </form>
        )}
      </section>

      <section className="section" aria-labelledby="alerts">
        <h2 className="section-title" id="alerts">
          End-of-day alerts
        </h2>
        <p className="section-note">
          After the close, FINN checks every holding against these limits and tells you if a
          filing explains the move.
        </p>
        {saved === "alerts" && <p className="notice">Alert limits saved.</p>}
        <form action={updateThresholds} className="panel">
          <div className="field">
            <label htmlFor="volume">Volume, times the 20-day average</label>
            <input id="volume" name="volume" type="number" step="0.1" min={FLOORS.volume} defaultValue={t.volume} />
          </div>
          <div className="field">
            <label htmlFor="price">Price move in a day, percent</label>
            <input id="price" name="price" type="number" step="0.5" min={FLOORS.price} defaultValue={t.price} />
          </div>
          <div className="field">
            <label htmlFor="sigma">Unusual move, standard deviations of daily returns</label>
            <input id="sigma" name="sigma" type="number" step="0.1" min={FLOORS.sigma} defaultValue={t.sigma} />
          </div>
          <div className="field">
            <label htmlFor="delivery">Delivery share, times its usual level</label>
            <input id="delivery" name="delivery" type="number" step="0.1" min={FLOORS.delivery} defaultValue={t.delivery} />
            <span className="help">Only checked when volume also crosses its limit.</span>
          </div>
          <button className="button" type="submit">
            Save alert limits
          </button>
        </form>
      </section>

      <section className="section" aria-labelledby="push">
        <h2 className="section-title" id="push">
          Notifications
        </h2>
        <PushToggle vapidKey={process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ?? ""} />
      </section>

      <p className="section-note">
        <Link href="/status">Data sources and freshness</Link>
      </p>
    </main>
  );
}
