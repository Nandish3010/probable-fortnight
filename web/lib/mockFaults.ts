// Fault injection for mock mode, so a test (or a person) can make a mocked route fail the way the
// real one would. Mock mode only: the body is behind the same inline env check as lib/mockData.ts,
// so none of this ships in a production bundle.
//
// A test sets localStorage "taal_mock_fault" before the page loads, e.g.
//   page.addInitScript(() => localStorage.setItem("taal_mock_fault",
//     JSON.stringify({ "/chat": { kind: "model_unavailable", retry_after_s: 2, times: 1 } })))
// Keys are path prefixes ("/chat", "/gaps", "/events"); the longest matching prefix wins. `times`
// limits how many calls fail (then the route behaves normally again); omit it to fail every call.
import { ApiError, type ApiErrorKind } from "./apiError";

export interface MockFault {
  kind: ApiErrorKind;
  retry_after_s?: number;
  times?: number;
}

const FAULT_KEY = "taal_mock_fault";

const STATUS_BY_KIND: Record<ApiErrorKind, number> = {
  network: 0,
  timeout: 0,
  http: 500,
  model_unavailable: 503,
  conflict: 409,
  not_found: 404,
  rate_limited: 429,
};

function readFaults(): Record<string, MockFault> | null {
  try {
    const raw = window.localStorage.getItem(FAULT_KEY);
    return raw ? (JSON.parse(raw) as Record<string, MockFault>) : null;
  } catch {
    return null;
  }
}

/** Called at the top of every mocked route. Counts the call (window.__taalMockCalls, which a test
 * can read to prove how many requests a click made) and throws the configured fault, if any. */
export async function mockGate(path: string): Promise<void> {
  if (process.env.NEXT_PUBLIC_TAAL_MOCK !== "1") return;
  if (typeof window === "undefined") return;
  const w = window as unknown as { __taalMockCalls?: Record<string, number> };
  w.__taalMockCalls = w.__taalMockCalls ?? {};
  w.__taalMockCalls[path] = (w.__taalMockCalls[path] ?? 0) + 1;

  const faults = readFaults();
  if (!faults) return;
  const key = Object.keys(faults)
    .filter((k) => path.startsWith(k))
    .sort((a, b) => b.length - a.length)[0];
  if (!key) return;
  const fault = faults[key];
  if (typeof fault.times === "number") {
    if (fault.times <= 0) return;
    faults[key] = { ...fault, times: fault.times - 1 };
    try {
      window.localStorage.setItem(FAULT_KEY, JSON.stringify(faults));
    } catch {
      // Storage blocked: the fault simply applies every time.
    }
  }
  throw new ApiError({
    kind: fault.kind,
    endpoint: path,
    status: STATUS_BY_KIND[fault.kind],
    retryAfterSeconds: fault.retry_after_s,
  });
}

const DELAY_KEY = "taal_mock_delay";

/** How long a mocked route waits before answering. A test sets localStorage "taal_mock_delay" to
 * e.g. {"/approve": 4000, "/chat": 9000} so a state that is normally over in a second (the
 * submitting steps and timer, a slow chat preview) stays on screen. Falls back to `fallbackMs`. */
export function mockDelayMs(path: string, fallbackMs: number): number {
  if (process.env.NEXT_PUBLIC_TAAL_MOCK !== "1" || typeof window === "undefined") return fallbackMs;
  try {
    const raw = window.localStorage.getItem(DELAY_KEY);
    if (!raw) return fallbackMs;
    const map = JSON.parse(raw) as Record<string, number>;
    const v = map[path];
    return typeof v === "number" && v >= 0 ? v : fallbackMs;
  } catch {
    return fallbackMs;
  }
}
