"use client";

import { usePathname } from "next/navigation";

/** The small footer of the screens that have none of their own: Deck, Repo and the practitioner
 * feedback form. The landing page carries a fuller footer, and the feedback form is the page those
 * links lead to, so neither renders this. */
export function SiteFooter() {
  const pathname = usePathname() ?? "";
  if (pathname === "/" || pathname.startsWith("/feedback")) return null;
  return (
    <footer className="footer site-footer" data-testid="site-footer">
      <div className="footer__links">
        <a href="https://github.com/Nandish3010/probable-fortnight/raw/main/docs/deck.pdf" target="_blank" rel="noreferrer">
          Deck
        </a>
        <a href="https://github.com/Nandish3010/probable-fortnight" target="_blank" rel="noreferrer">
          Repo
        </a>
        <a href="/feedback">Practitioner feedback</a>
      </div>
    </footer>
  );
}
