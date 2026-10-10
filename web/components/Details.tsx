import type { ReactNode } from "react";
import { Icon } from "./icons";
import styles from "./Details.module.css";

/** "Show technical details": a native disclosure that holds raw ids, JSON and trace so the plain
 * language stays on the surface and the exact value is one click away. Closed by default.
 *
 * `variant="card"` is the decision card's own disclosure (components/PlayCard.tsx): a 44px summary
 * line that already carries the result ("Details · 8 checks: 5 passed, 3 not applicable") and a
 * chevron, so a person who never opens it still reads what is inside.
 *
 * The plain variant (raw ids, JSON, trace) is the same kind of disclosure: a 44px summary with a
 * chevron that turns when it opens. `inline` stays a one-line affordance for table cells. */
export function Details({
  children,
  summary = "Show technical details",
  inline = false,
  variant = "plain",
  defaultOpen = false,
  testId,
}: {
  children: ReactNode;
  summary?: ReactNode;
  /** Compact variant for table cells and one-line rows. */
  inline?: boolean;
  variant?: "plain" | "card";
  /** Open on first render (e.g. when a check failed); the reader can still close it. */
  defaultOpen?: boolean;
  testId?: string;
}) {
  const isCard = variant === "card";
  const chevron = isCard || !inline;
  return (
    <details
      className={`${styles.details} ${inline ? styles.inline : ""} ${isCard ? styles.card : ""}`}
      data-testid={testId}
      open={defaultOpen || undefined}
    >
      <summary className={styles.summary}>
        {chevron ? <Icon name="chevron-down" size={16} className={styles.chevron} /> : null}
        {summary}
      </summary>
      <div className={isCard ? styles.cardBody : styles.body}>{children}</div>
    </details>
  );
}
