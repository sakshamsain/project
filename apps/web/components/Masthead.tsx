import Link from "next/link";
import type { SessionUser } from "@/lib/auth";

/** The top of every page: FINN's stamp on a phone (on a wide screen it sits in the rail),
 *  search and the account. `note` is kept for callers; the tab bar says where you are. */
export default function Masthead({ user }: { user?: SessionUser | null; note?: string }) {
  const initial = user ? (user.name || user.email).trim().charAt(0).toUpperCase() : null;
  return (
    <header className="masthead">
      <Link className="wordmark" href="/">
        FINN
      </Link>
      <div className="mast-right">
        <Link href="/search" className="icon-btn" aria-label="Find a company">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <circle cx="10.5" cy="10.5" r="6" />
              <path d="M15 15l5 5" />
            </g>
          </svg>
        </Link>
        <Link
          href={user ? "/settings#account" : "/signin"}
          className={user ? "icon-btn avatar" : "icon-btn"}
          aria-label={user ? `Your account, ${user.email}` : "Sign in"}
        >
          {initial ?? (
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                <circle cx="12" cy="8.5" r="3.5" />
                <path d="M5 20c1.2-3.6 4-5 7-5s5.8 1.4 7 5" />
              </g>
            </svg>
          )}
        </Link>
      </div>
    </header>
  );
}
