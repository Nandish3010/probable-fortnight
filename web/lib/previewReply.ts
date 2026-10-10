// Turns the first /chat reply into what the Approve preview shows. Pure: tests/e2e/lang.spec.ts.
import { replyLanguage, type ReplyLanguage } from "./lang";
import type { ChatEnvelope, DemoCustomer } from "./types";

/** True when the reply carries no offer from any play. A customer outside the treated group gets a
 * real reply that says there are no offers; the preview shows it as it is, with a caption. */
export function hasNoOffer(envelope: ChatEnvelope): boolean {
  return !(envelope.citations ?? []).some((c) => c.type === "play");
}

export interface PreviewReply {
  language: ReplyLanguage;
  offAudience: boolean;
}

/** `customer` is the demo-customer record (language, holdout role) when it could be read in time. */
export function describeReply(envelope: ChatEnvelope, customer: DemoCustomer | null): PreviewReply {
  const preferred = customer?.language ?? envelope.language ?? null;
  return {
    language: replyLanguage(envelope.text, preferred),
    offAudience: customer?.role === "holdout" || hasNoOffer(envelope),
  };
}
