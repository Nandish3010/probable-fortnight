// How the Approve result talks to the chat panel without either importing the other. The result's
// follow-up buttons dispatch one typed window event; a mounted ChatPanel answers it by setting
// `handled` on the detail. When nothing answers (the Desk has no chat panel), the caller opens /chat.

/** The customer the chat panel opens on until a play is approved, and the preview's fallback when the
 * customer list cannot be read. After an approval the customer is chosen per play
 * (lib/treatedPersona.ts), because Meena is only in the chips audience. */
export const DEMO_CUSTOMER_ID = "CUST-MEENA";
/** The opening message of the demo, sent by the preview and by the "Chat as ..." follow-up. */
export const DEMO_MESSAGE = "Any offers today?";
/** The same question in Kannada ("Is there any offer today?"), the opening message for a Kannada customer. */
export const DEMO_MESSAGE_KN = "ಇಂದು ಯಾವುದಾದರೂ ಆಫರ್ ಇದೆಯಾ?";

/** The opening message for a customer: Kannada for a Kannada customer ("kn", or "kannada"), English for
 * everyone else and for an unknown language. */
export function demoMessageFor(language: string | null | undefined): string {
  const l = (language ?? "").trim().toLowerCase();
  return l === "kn" || l === "kannada" ? DEMO_MESSAGE_KN : DEMO_MESSAGE;
}

export const CHAT_REQUEST_EVENT = "taal:chat-request";

export type ChatRequestAction =
  /** Scroll to the chat panel, focus the composer and pre-fill the message (nothing is sent). */
  | "prefill"
  /** Scroll to the chat panel, switch to the customer and send the message: the offer arrives in one
   * click. A second request for the same customer and message is ignored, so a double click sends once. */
  | "ask"
  /** Switch to the holdout persona and send the message. */
  | "holdout";

export interface ChatRequestDetail {
  action: ChatRequestAction;
  message: string;
  /** The customer to chat as; the panel switches to them when it has them. */
  customerId?: string;
  /** Set to true by the listener that took the request. */
  handled: boolean;
}

/** Dispatches the request; returns whether a ChatPanel took it. */
export function requestChat(action: ChatRequestAction, message: string = DEMO_MESSAGE, customerId?: string): boolean {
  if (typeof window === "undefined") return false;
  const detail: ChatRequestDetail = { action, message, customerId, handled: false };
  window.dispatchEvent(new CustomEvent<ChatRequestDetail>(CHAT_REQUEST_EVENT, { detail }));
  return detail.handled;
}

/** The /chat URL that carries the same request, for pages with no chat panel. */
export function chatUrlFor(action: ChatRequestAction, customerId?: string): string {
  if (action === "holdout") return "/chat?as=holdout";
  if (action === "ask") return customerId ? `/chat?as=ask&customer=${encodeURIComponent(customerId)}` : "/chat?as=ask";
  return customerId ? `/chat?as=prefill&customer=${encodeURIComponent(customerId)}` : "/chat?as=prefill";
}
