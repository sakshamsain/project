"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const TABS = [
  {
    href: "/",
    label: "Today",
    icon: (
      <path d="M5 4h11l3 3v13H5zM8 9h8M8 13h8M8 17h5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
    ),
  },
  {
    href: "/pulse",
    label: "Pulse",
    icon: <path d="M3 13h4l2-6 4 11 2-5h6" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" strokeLinecap="round" />,
  },
  {
    href: "/inbox",
    label: "Inbox",
    icon: (
      <g fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" strokeLinecap="round">
        <path d="M4 13l2.5-7h11L20 13v6H4z" />
        <path d="M4 13h4.5l1 2h5l1-2H20" />
      </g>
    ),
  },
  {
    href: "/research",
    label: "Research",
    icon: (
      <g fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
        <circle cx="10.5" cy="10.5" r="5.5" />
        <path d="M15 15l5 5" />
      </g>
    ),
  },
  {
    href: "/settings",
    label: "Settings",
    icon: (
      <g fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
        <path d="M4 7h10M18 7h2M4 17h4M12 17h8" />
        <circle cx="16" cy="7" r="2" />
        <circle cx="10" cy="17" r="2" />
      </g>
    ),
  },
];

function useUnread(path: string): number {
  const [n, setN] = useState(0);
  useEffect(() => {
    let stop = false;
    const load = () =>
      fetch("/api/inbox", { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : { unread: 0 }))
        .then((j: { unread: number }) => !stop && setN(j.unread))
        .catch(() => undefined);
    void load();
    const cleared = () => setN(0);
    window.addEventListener("finn:inbox-seen", cleared);
    return () => {
      stop = true;
      window.removeEventListener("finn:inbox-seen", cleared);
    };
  }, [path]);
  return path.startsWith("/inbox") ? 0 : n;
}

export default function Tabs() {
  const path = usePathname();
  const unread = useUnread(path);
  const active = (href: string) =>
    href === "/" ? path === "/" || path.startsWith("/event") || path.startsWith("/company") : path.startsWith(href);
  return (
    <nav className="tabs" aria-label="Sections">
      <ul>
        {TABS.map((t) => (
          <li key={t.href}>
            <Link href={t.href} aria-current={active(t.href) ? "page" : undefined}>
              <svg viewBox="0 0 24 24" aria-hidden="true">
                {t.icon}
              </svg>
              {t.label}
              {t.href === "/inbox" && unread > 0 && (
                <span className="badge" aria-label={`${unread} new`}>
                  {unread > 9 ? "9+" : unread}
                </span>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
