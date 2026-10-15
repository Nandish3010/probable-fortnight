// The plain-language wording for each failure kind. Pure (no React, no CSS) so a node-level test
// can pin the exact copy; components/ErrorCard.tsx renders it.
import type { ApiError, ApiErrorKind } from "./apiError";

/** Seconds the UI asks a visitor to wait when the server did not say. */
export const DEFAULT_RETRY_SECONDS = 30;

export interface ErrorCopy {
  title: string;
  body: string;
}

/** A spend cap, not a fault: which cap, and how long to wait (the API sends the seconds in Retry-After). */
function rateLimited(error: ApiError): ErrorCopy {
  const wait = error.retryAfterSeconds !== undefined ? `about ${Math.ceil(error.retryAfterSeconds)} seconds` : "a moment";
  if (error.rateScope === "shared") {
    return { title: "The demo is busy", body: `The demo is busy right now (shared usage limit). Please wait ${wait} and try again.` };
  }
  if (error.rateScope === "visitor") {
    return { title: "Feature limit reached", body: `You have used the limit for this feature. Please wait ${wait}.` };
  }
  return { title: "Too many requests", body: `Please wait ${wait} and try again.` };
}

/** The plain-language copy for each failure kind. Exported so a unit test can pin the wording. */
export function errorCopy(error: ApiError): ErrorCopy {
  const seconds = error.retryAfterSeconds ?? DEFAULT_RETRY_SECONDS;
  const copy: Record<ApiErrorKind, ErrorCopy> = {
    network: {
      title: "Can't reach the Taal service",
      body: "The demo server isn't answering. This usually clears in a minute.",
    },
    timeout: {
      title: "This is taking longer than expected",
      body: "The server did not answer in time. Trying again usually works.",
    },
    model_unavailable: {
      title: "The AI model is busy",
      body: `The model that writes the replies is overloaded right now. Try again in ${seconds} seconds.`,
    },
    conflict: {
      title: "Already approved",
      body: "This play was already approved in your session, so there is nothing more to submit.",
    },
    not_found: {
      title: "This demo session was restarted",
      body: "Your sandbox was reset. Run the demo again from the start.",
    },
    rate_limited: rateLimited(error),
    http: {
      title: "Something went wrong",
      body: error.status > 0
        ? `The server answered with an error (${error.status}). Try again, and if it keeps happening use the recorded result.`
        : "Something unexpected happened. Try again, and if it keeps happening use the recorded result.",
    },
  };
  return copy[error.kind];
}
