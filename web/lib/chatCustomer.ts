"use client";

// The customer currently selected in the /chat panel's picker, shared with the persona bar and the
// stepper's Offer sublabel so all three name the same person. The chat panel publishes the first
// name; nothing is persisted. Null until a customer is selected (the default stays "Meena") and
// again once the panel unmounts. Only /chat reads it: other routes keep their own persona.
import { useSyncExternalStore } from "react";

let current: string | null = null;
const listeners = new Set<() => void>();

export function setChatCustomerName(name: string | null): void {
  if (name === current) return;
  current = name;
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** The first name of the customer selected in the chat panel, or null. */
export function useChatCustomerName(): string | null {
  return useSyncExternalStore(subscribe, () => current, () => null);
}
