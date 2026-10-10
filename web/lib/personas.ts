// Who each screen is for (E4, ux_plan.md section 3). Pure data and two small functions, so the
// mapping is unit-tested in node (tests/e2e/persona-bar.spec.ts) and the bar cannot drift from the
// stepper's persona names (lib/progress.ts STEPS).

export type PersonaId = "priya" | "arjun" | "meena";

export interface Persona {
  id: PersonaId;
  name: string;
  role: string;
  /** The screen "View as" opens: a plain link, never client state. */
  href: string;
}

export const PERSONAS: readonly Persona[] = [
  { id: "priya", name: "Priya", role: "node manager", href: "/phone" },
  { id: "arjun", name: "Arjun", role: "demand planner", href: "/" },
  { id: "meena", name: "Meena", role: "customer", href: "/chat" },
];

const BY_PATH: Record<string, PersonaId> = {
  "/": "arjun",
  "/desk": "arjun",
  "/outcomes": "arjun",
  "/phone": "priya",
  "/chat": "meena",
};

export function personaById(id: PersonaId): Persona {
  return PERSONAS.find((p) => p.id === id) as Persona;
}

/** The persona a route is written for; null off the five screens (feedback, dev pages, 404). */
export function personaForPath(pathname: string | null | undefined): Persona | null {
  if (!pathname) return null;
  const clean = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  const id = BY_PATH[clean];
  return id ? personaById(id) : null;
}

/** The accessible name of a "View as" chip: "View as Priya, node manager". */
export function viewAsName(p: Persona): string {
  return `View as ${p.name}, ${p.role}`;
}

/** The persona's initial, for the avatar. */
export function initialOf(p: Persona): string {
  return p.name.charAt(0).toUpperCase();
}
