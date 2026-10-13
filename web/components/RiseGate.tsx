"use client";

import { usePathname } from "next/navigation";
import { useEffect, useLayoutEffect } from "react";

// The entrance (globals.css, "motion") is for the blocks a page paints first. A block that arrives
// later (a skeleton replaced by the loaded content) must not rise in on its own, or a transform
// would stay on it well after the page's entrance is over. So the entrance is open for 500 ms from
// a route's first paint (the longest rise ends at 440 ms), then html[data-rise="off"] stops it:
// whatever is still moving jumps to its final state and nothing is applied afterwards.
const WINDOW_MS = 500;
const useBeforePaint = typeof window === "undefined" ? useEffect : useLayoutEffect;

export function RiseGate() {
  const pathname = usePathname();
  useBeforePaint(() => {
    const root = document.documentElement;
    delete root.dataset.rise;
    const timer = window.setTimeout(() => {
      root.dataset.rise = "off";
    }, WINDOW_MS);
    return () => window.clearTimeout(timer);
  }, [pathname]);
  return null;
}
