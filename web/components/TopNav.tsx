"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Stepper } from "./Stepper";
import { stepForPath } from "../lib/progress";

/** The bar on every route: the brand (a link home) on the left and, on the five screens of the
 * judge path, the stepper in the nav area. A route off that path (the practitioner feedback form,
 * the dev pages, a missing page) gets the brand and a way back instead. */
export default function TopNav() {
  const pathname = usePathname();
  const current = stepForPath(pathname);
  return (
    <header className="top-nav">
      <div className="top-nav__inner">
        <Link href="/" className="top-nav__brand" aria-label="Taal, home">
          <span className="top-nav__mark" aria-hidden="true" />
          Taal
        </Link>
        {current ? (
          <Stepper current={current} />
        ) : (
          <Link href="/" className="top-nav__back">
            Back to demo
          </Link>
        )}
      </div>
    </header>
  );
}
