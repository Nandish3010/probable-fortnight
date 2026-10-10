"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PERSONAS, initialOf, personaForPath, viewAsName, type Persona } from "../lib/personas";
import styles from "./PersonaBar.module.css";

/** A coloured circle with the persona's initial. Inline SVG, decorative (aria-hidden): the name is
 * always written next to it. No image files. */
function Avatar({ persona, size }: { persona: Persona; size: number }) {
  return (
    <svg
      className={styles.avatar}
      data-persona={persona.id}
      width={size}
      height={size}
      viewBox="0 0 32 32"
      aria-hidden="true"
      focusable="false"
    >
      <circle cx="16" cy="16" r="16" />
      <text x="16" y="16" textAnchor="middle" dominantBaseline="central" fontSize="16">
        {initialOf(persona)}
      </text>
    </svg>
  );
}

/** Who this screen is for, and a way to see the demo as someone else (E4). The "View as" chips are
 * plain links to that persona's screen, so the browser Back button and a shared URL both work and
 * nothing is held in client state. */
export function PersonaBar() {
  const pathname = usePathname();
  const current = personaForPath(pathname);
  if (!current) return null;
  const others = PERSONAS.filter((p) => p.id !== current.id);
  return (
    <div className={styles.bar} data-testid="persona-bar" data-persona={current.id}>
      <div className={styles.inner}>
        <p className={styles.who} data-testid="persona-who">
          <Avatar persona={current} size={24} />
          <span>
            <span className={styles.for}>
              <span className={styles.forLong}>This screen is for </span>
            </span>
            <span className={styles.name}>{current.name}</span>
            <span className={styles.role} data-testid="persona-role">, {current.role}</span>
          </span>
        </p>
        <nav className={styles.chips} aria-label="View as">
          <span className={styles.viewAs} aria-hidden="true">View as</span>
          {others.map((p) => (
            <Link key={p.id} href={p.href} className={styles.chip} aria-label={viewAsName(p)} data-persona={p.id} data-testid={`view-as-${p.id}`}>
              <span className={styles.pill}>
                <Avatar persona={p} size={22} />
                {p.name}
              </span>
            </Link>
          ))}
        </nav>
      </div>
    </div>
  );
}
