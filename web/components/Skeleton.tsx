import type { CSSProperties } from "react";
import styles from "./Skeleton.module.css";

/** A placeholder block that holds the final size while something loads (an image, a card), so
 * nothing jumps when the real content arrives. Decorative: whatever loads announces itself. */
export function Skeleton({ width, height, radius, className = "" }: { width?: number | string; height?: number | string; radius?: number | string; className?: string }) {
  const style: CSSProperties = { width, height, borderRadius: radius };
  return <span className={`${styles.skeleton} ${className}`} style={style} aria-hidden="true" data-testid="skeleton" />;
}
