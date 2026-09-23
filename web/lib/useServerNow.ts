"use client";

import { useEffect, useState } from "react";
import { getHealth } from "./api";

/** The server's pinned clock (TAAL_NOW for the demo tenant, or its real wall clock otherwise),
 * fetched once from /health. Any day-countdown math against seeded deadline dates (GapCard's
 * daysUntil) must use this instead of `new Date()` -- the browser's local clock drifts away from
 * the snapshot the demo tenant is frozen at and silently floors every countdown to 0. Returns
 * undefined until the first successful /health response lands. */
export function useServerNow(): Date | undefined {
  const [now, setNow] = useState<Date | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((h) => {
        if (!cancelled && h.server_now) {
          const parsed = new Date(h.server_now);
          if (!Number.isNaN(parsed.getTime())) setNow(parsed);
        }
      })
      .catch(() => {
        // Leave `now` undefined; GapCard/daysUntil fall back to the browser clock rather than
        // block rendering on a health check.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return now;
}
