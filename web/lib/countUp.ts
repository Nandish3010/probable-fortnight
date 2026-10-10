// The count-up on the Approve result (design_spec.md 6.2): requestAnimationFrame, ease-out quartic,
// ends exactly on the target. The maths is pure so a node test can pin it; the hook only drives it.
import { useEffect, useState } from "react";

/** 0 to 1, fast at the start, settling at the end: 1 - (1 - t)^4. Clamped. */
export function easeOutQuart(t: number): number {
  const c = Math.min(1, Math.max(0, t));
  return 1 - Math.pow(1 - c, 4);
}

/** The value shown `elapsedMs` after the count-up starts. At or after `durationMs` it is exactly
 * `target` (not a rounded neighbour), so the settled figure is the canonical one. */
export function countUpValue(target: number, elapsedMs: number, durationMs: number): number {
  if (!(durationMs > 0) || elapsedMs >= durationMs) return target;
  if (elapsedMs <= 0) return 0;
  return target * easeOutQuart(elapsedMs / durationMs);
}

/** While `run` is true, counts from 0 to `target` over `durationMs` after `delayMs`; when `run` is
 * false the value is `target`. Initial render with `run` true shows 0, so there is no flash of the
 * final figure before the count starts. */
export function useCountUp(target: number, run: boolean, delayMs: number, durationMs: number): number {
  const [value, setValue] = useState(run ? 0 : target);
  useEffect(() => {
    if (!run) {
      setValue(target);
      return;
    }
    setValue(0);
    const start = performance.now() + delayMs;
    let raf = 0;
    const tick = (now: number) => {
      const elapsed = now - start;
      if (elapsed < 0) {
        raf = requestAnimationFrame(tick);
        return;
      }
      setValue(countUpValue(target, elapsed, durationMs));
      if (elapsed < durationMs) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, run, delayMs, durationMs]);
  return value;
}
