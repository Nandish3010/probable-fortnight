"use client";

import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Judge mode" },
  { href: "/desk", label: "Play Desk" },
  { href: "/phone", label: "Phone view" },
  { href: "/chat", label: "Chat" },
  { href: "/stylist", label: "Stylist" },
  { href: "/trends", label: "Trends" },
  { href: "/outcomes", label: "Outcomes" },
];

export default function TopNav() {
  const pathname = usePathname();
  return (
    <nav className="top-nav">
      <span className="top-nav__brand">
        <span className="top-nav__mark" aria-hidden="true" />
        Taal
      </span>
      {LINKS.map((link) => (
        <a key={link.href} href={link.href} aria-current={pathname === link.href ? "page" : undefined}>
          {link.label}
        </a>
      ))}
    </nav>
  );
}
