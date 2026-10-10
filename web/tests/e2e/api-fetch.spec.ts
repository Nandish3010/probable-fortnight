import { test, expect } from "@playwright/test";
import { ApiError, DEFAULT_TIMEOUT_MS, apiFetch, timeoutFor } from "../../lib/api";
import { errorCopy } from "../../lib/errorCopy";
import { toApiError } from "../../lib/apiError";

// The request wrapper and its error mapping, with fetch stubbed. No browser, no server.
// (apiFetch itself never looks at mock mode, so the NEXT_PUBLIC_TAAL_MOCK=1 of `npm test` is irrelevant.)

type FetchImpl = (url: string, init?: RequestInit) => Promise<Response>;

async function withFetch<T>(impl: FetchImpl, run: () => Promise<T>): Promise<T> {
  const original = globalThis.fetch;
  globalThis.fetch = impl as unknown as typeof fetch;
  try {
    return await run();
  } finally {
    globalThis.fetch = original;
  }
}

const json = (body: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" }, ...init });

async function failure(impl: FetchImpl, path = "/x", opts?: Parameters<typeof apiFetch>[2]): Promise<ApiError> {
  return withFetch(impl, async () => {
    try {
      await apiFetch(path, undefined, opts);
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      return e as ApiError;
    }
    throw new Error("expected apiFetch to throw");
  });
}

test.describe("timeoutFor", () => {
  test("per-endpoint budgets", () => {
    expect(DEFAULT_TIMEOUT_MS).toBe(10_000);
    expect(timeoutFor("/gaps?limit=1000")).toBe(10_000);
    expect(timeoutFor("/health")).toBe(10_000);
    expect(timeoutFor("/approve")).toBe(60_000);
    expect(timeoutFor("/plan")).toBe(100_000);
    expect(timeoutFor("/rerun")).toBe(100_000);
    expect(timeoutFor("/rerun/abc")).toBe(100_000);
    expect(timeoutFor("/chat")).toBe(20_000);
    expect(timeoutFor("/capture")).toBe(20_000);
    expect(timeoutFor("/capture/confirm")).toBe(20_000);
    expect(timeoutFor("/measure")).toBe(30_000);
    // prefixes only match whole path segments
    expect(timeoutFor("/approvals")).toBe(10_000);
    expect(timeoutFor("/chatter")).toBe(10_000);
  });
});

test.describe("apiFetch", () => {
  test("returns the JSON body and sends the visitor header with credentials", async () => {
    let seen: { url: string; init?: RequestInit } | null = null;
    const body = await withFetch(
      async (url, init) => {
        seen = { url, init };
        return json({ ok: true });
      },
      () => apiFetch<{ ok: boolean }>("/ping", { method: "POST", body: "{}" }),
    );
    expect(body).toEqual({ ok: true });
    expect(seen!.url.endsWith("/ping")).toBe(true);
    expect(seen!.init?.credentials).toBe("include");
    const headers = new Headers(seen!.init?.headers);
    expect(headers.get("X-Taal-Visitor")).toBeTruthy();
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  test("503 {error: model_unavailable} is model_unavailable, with Retry-After taken from the header first", async () => {
    const e = await failure(async () =>
      json({ error: "model_unavailable", model: "gemini-3.5-flash", retry_after_s: 30 }, { status: 503, headers: { "Retry-After": "17" } }),
    "/chat");
    expect(e.kind).toBe("model_unavailable");
    expect(e.status).toBe(503);
    expect(e.retryAfterSeconds).toBe(17);
    expect(e.endpoint).toBe("/chat");
  });

  test("model_unavailable falls back to the body's retry_after_s when there is no header", async () => {
    const e = await failure(async () => json({ error: "model_unavailable", retry_after_s: 30 }, { status: 503 }));
    expect(e.kind).toBe("model_unavailable");
    expect(e.retryAfterSeconds).toBe(30);
  });

  test("a 503 that is not the model being busy is a plain http error", async () => {
    expect((await failure(async () => json({ detail: "down" }, { status: 503 }))).kind).toBe("http");
    expect((await failure(async () => new Response("<html>bad gateway</html>", { status: 503 }))).kind).toBe("http");
  });

  test("409 -> conflict, 404 -> not_found, 429 -> rate_limited (with Retry-After), other -> http", async () => {
    expect((await failure(async () => json({}, { status: 409 }))).kind).toBe("conflict");
    expect((await failure(async () => json({}, { status: 404 }))).kind).toBe("not_found");
    const limited = await failure(async () => json({}, { status: 429, headers: { "Retry-After": "12" } }));
    expect(limited.kind).toBe("rate_limited");
    expect(limited.retryAfterSeconds).toBe(12);
    const server = await failure(async () => json({ detail: "boom" }, { status: 500 }), "/gaps?limit=5");
    expect(server.kind).toBe("http");
    expect(server.status).toBe(500);
    expect(server.endpoint).toBe("/gaps"); // the query string is not part of the endpoint
  });

  test("a CORS block or refused connection (TypeError) is a network error", async () => {
    const e = await failure(async () => {
      throw new TypeError("Failed to fetch");
    });
    expect(e.kind).toBe("network");
    expect(e.status).toBe(0);
  });

  test("a server that never answers times out at the budget", async () => {
    const started = Date.now();
    const e = await failure(
      (_url, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
      "/gaps",
      { timeoutMs: 60 },
    );
    expect(e.kind).toBe("timeout");
    expect(Date.now() - started).toBeLessThan(2000);
  });

  test("the caller's own abort is rethrown as an abort, not mapped to a timeout or network error", async () => {
    const controller = new AbortController();
    const result = withFetch(
      (_url, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
      () => apiFetch("/events/r1", undefined, { signal: controller.signal }),
    );
    controller.abort();
    await expect(result).rejects.toMatchObject({ name: "AbortError" });
  });
});

test.describe("toApiError and the ErrorCard copy", () => {
  test("anything thrown becomes an ApiError", () => {
    expect(toApiError(new TypeError("x"), "/a").kind).toBe("network");
    expect(toApiError(new Error("x"), "/a").kind).toBe("http");
    const same = new ApiError({ kind: "conflict", endpoint: "/approve", status: 409 });
    expect(toApiError(same)).toBe(same);
  });

  test("exact copy per kind", () => {
    const e = (kind: ApiError["kind"], extra: Partial<ConstructorParameters<typeof ApiError>[0]> = {}) =>
      new ApiError({ kind, endpoint: "/x", ...extra });
    expect(errorCopy(e("network"))).toEqual({
      title: "Can't reach the Taal service",
      body: "The demo server isn't answering. This usually clears in a minute.",
    });
    expect(errorCopy(e("timeout")).title).toBe("This is taking longer than expected");
    expect(errorCopy(e("model_unavailable")).title).toBe("The AI model is busy");
    expect(errorCopy(e("model_unavailable")).body).toContain("Try again in 30 seconds");
    expect(errorCopy(e("model_unavailable", { retryAfterSeconds: 7 })).body).toContain("Try again in 7 seconds");
    expect(errorCopy(e("conflict")).title).toBe("Already approved");
    expect(errorCopy(e("not_found"))).toMatchObject({
      title: "This demo session was restarted",
      body: "Your sandbox was reset. Run the demo again from the start.",
    });
    expect(errorCopy(e("rate_limited")).title).toBe("Too many requests");
    expect(errorCopy(e("http", { status: 500 })).title).toBe("Something went wrong");
  });
});
