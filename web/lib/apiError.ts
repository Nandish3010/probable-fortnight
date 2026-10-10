// The one error type the API layer throws. `kind` is what the UI switches on (components/
// ErrorCard.tsx); `status` is the HTTP status, or 0 when no response arrived.

export type ApiErrorKind =
  | "network"
  | "timeout"
  | "http"
  | "model_unavailable"
  | "conflict"
  | "not_found"
  | "rate_limited";

export class ApiError extends Error {
  kind: ApiErrorKind;
  status: number;
  /** From the Retry-After header, else the body's retry_after_s; undefined when neither was sent. */
  retryAfterSeconds?: number;
  /** The request path without its query string, e.g. "/approve". */
  endpoint: string;

  constructor(init: {
    kind: ApiErrorKind;
    endpoint: string;
    status?: number;
    retryAfterSeconds?: number;
    message?: string;
  }) {
    super(init.message ?? `${init.endpoint} -> ${init.kind}${init.status ? ` (${init.status})` : ""}`);
    this.name = "ApiError";
    this.kind = init.kind;
    this.status = init.status ?? 0;
    this.retryAfterSeconds = init.retryAfterSeconds;
    this.endpoint = init.endpoint;
  }
}

/** Maps an HTTP failure to an ApiError. 503 maps to model_unavailable only when the body says so
 * ({"error": "model_unavailable"}); any other 503 is a plain http error. */
export function errorFromResponse(
  endpoint: string,
  status: number,
  body: unknown,
  retryAfterHeader: string | null,
): ApiError {
  const b = body && typeof body === "object" ? (body as Record<string, unknown>) : {};
  const headerSeconds = retryAfterHeader !== null && retryAfterHeader.trim() !== "" ? Number(retryAfterHeader) : NaN;
  const bodySeconds = typeof b.retry_after_s === "number" ? b.retry_after_s : NaN;
  const retryAfterSeconds = [headerSeconds, bodySeconds].find((n) => Number.isFinite(n) && n >= 0);

  let kind: ApiErrorKind = "http";
  if (status === 503 && b.error === "model_unavailable") kind = "model_unavailable";
  else if (status === 409) kind = "conflict";
  else if (status === 404) kind = "not_found";
  else if (status === 429) kind = "rate_limited";
  return new ApiError({ kind, endpoint, status, retryAfterSeconds });
}

/** Anything thrown becomes an ApiError so the UI has one shape to render. A TypeError is what
 * fetch() throws for a CORS block, a refused connection or a dropped stream. */
export function toApiError(e: unknown, endpoint = ""): ApiError {
  if (e instanceof ApiError) return e;
  if (e instanceof TypeError) return new ApiError({ kind: "network", endpoint, message: e.message });
  if (e instanceof DOMException && e.name === "TimeoutError") return new ApiError({ kind: "timeout", endpoint });
  return new ApiError({ kind: "http", endpoint, message: e instanceof Error ? e.message : String(e) });
}
