"use client";

import { useSyncExternalStore } from "react";

/** The width below which Taal lays out for a phone (design_spec.md section 2: breakpoint 768). */
export const PHONE_QUERY = "(max-width: 767px)";

/** Follows a CSS media query. The server render, and the first client render while hydrating, say
 * "no match" (the desktop layout); the browser's answer replaces it straight after hydration. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      if (typeof window === "undefined" || !window.matchMedia) return () => {};
      const mq = window.matchMedia(query);
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    },
    () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : false),
    () => false,
  );
}

export function useIsPhone(): boolean {
  return useMediaQuery(PHONE_QUERY);
}

/** True when the browser is laid out as a phone right now (not reactive). */
export function isPhoneNow(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia && window.matchMedia(PHONE_QUERY).matches;
}
