"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

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

export default function Tabs() {
  const path = usePathname();
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
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
