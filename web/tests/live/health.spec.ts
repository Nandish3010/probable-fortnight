import { test, expect } from "@playwright/test";

// web/app/health/route.ts: a live smoke-test target for .github/workflows/smoke.yml -- confirms
// the Next.js service itself is up and knows which API it is configured to talk to, independent
// of whether that API is reachable.
test.describe("web: /health", () => {
  test("returns ok with the service's own version and configured api_base", async ({ request, baseURL }) => {
    const res = await request.get("/health");
    expect(res.status()).toBe(200);
    expect(res.headers()["cache-control"]).toContain("no-store");
    const body = await res.json();
    expect(body.status).toBe("ok");
    expect(body.service).toBe("taal-web");
    expect(typeof body.version).toBe("string");
    expect(body.version.length).toBeGreaterThan(0);
    expect(typeof body.api_base).toBe("string");
  });
});
