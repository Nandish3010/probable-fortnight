# Taal — web (`web/`)

Next.js 15 App Router front end for Taal: the judge-mode landing, Play Desk, phone
capture view, Meena chat, and Outcomes. See `docs/DECISIONS.md` §5.6, §9, §10 and §11a for
the product spec this implements.

## Run it

```bash
cd web
npm ci --no-audit --no-fund
npm run dev            # http://localhost:3100 style dev server, mock mode via .env.local
```

Copy `.env.example` to `.env.local` to pick the API base URL and mock mode. Two env vars:

- `NEXT_PUBLIC_TAAL_API_URL` — base URL of the Taal API (default `http://localhost:8080`).
- `NEXT_PUBLIC_TAAL_MOCK` — `1` serves every route from the static fixtures under
  `web/mocks/*.json` instead of calling the API. No backend needed in this mode.

### Mock mode

`npm test` sets `NEXT_PUBLIC_TAAL_MOCK=1` automatically and runs the whole app against
`web/mocks/`. To browse the app in mock mode by hand:

```bash
NEXT_PUBLIC_TAAL_MOCK=1 npm run dev
```

Every mock file mirrors the TypeScript contracts in `lib/types.ts` exactly (`Play`, `Gap`,
`ChatEnvelope`, `ApproveResponse`, `Outcome`, …). Chat answers in mock mode depend on the
message text: "offers" returns the bundle offer (en + kn, with the best-before date),
"Cola Zero" returns the out-of-stock substitution list, "STOP" returns the opt-out
confirmation, anything else returns a generic prompt.

## Commands

```bash
npm run typecheck   # tsc --noEmit
npm run build       # next build
npm test            # Playwright, mock mode, pre-installed Chromium
npm run test:headed # same, headed
```

Playwright uses the Chromium under `PLAYWRIGHT_BROWSERS_PATH` (`/opt/pw-browsers`); it is
never installed by this project (`playwright install` must not be run here).

## Pages

| Route | What it shows |
|---|---|
| `/` | Judge-mode landing: top band + reset, "Run the 60-second beat" (gap card → pre-proposed play → Approve → forecast chart), "Chat as Meena" panel, three cards to Play Desk / Phone view / Outcomes, footer with the what-is-simulated box, tenant size and health strip. |
| `/desk` | Play Desk: inbox ranked by rupees at stake, the full play card (target, mechanic, audience, bilingual copy, expected outcome with CI, counterfactual bars, guardrails, "Why this play?" drawer, editable rationale, holdout slider, Approve), the trace panel (replay at 4x from the event log) and the policy editor ("Change policy → re-plan"). |
| `/phone` | Priya's capture flow: node selector, sample pallet photos (plus an experimental own-upload), the vision intake table with confirmation questions, the gap card for that node, Approve, and the post-approve execution checklist. Mic button is present but disabled. |
| `/chat` | Full-page version of the Meena chat panel used in the landing hero. |
| `/outcomes` | Per-play treated vs holdout table, lift with CI when measured (never shown for `unmeasured`), waste avoided, the CEO number ("net margin recovered per ₹1 of discount vs holdout"), the data-label badge, and the Looker link. |

## The LIVE / REPLAY convention

Every panel that shows a result carries a `Badge` (`components/Badge.tsx`):

- **LIVE** — a real call was made (or, in mock mode, a call whose *real* counterpart is a
  live call: Approve and Chat).
- **REPLAY** — a recorded/golden result (Sense's gaps, the Planner's pre-proposed play, the
  event trace, past plays in the inbox).
- **REAL PILOT** / **SYNTHETIC** — the data-provenance label used on Outcomes rows.

In mock mode every panel is labelled REPLAY except Approve and Chat, which are labelled
LIVE (mock) — the same convention the running app uses once wired to the real backend,
where a failed live call falls back to the recorded result with a visible
"showing recorded result (live call failed)" note rather than a blank panel.

## Per-visitor sandbox

`lib/visitor.ts` keeps a random id in `localStorage` (`taal_visitor`); `lib/api.ts` sends it
as the `X-Taal-Visitor` header on every request (with `credentials: "include"`) so the
backend can scope Firestore state per visitor. "Reset demo data" on the landing page only
touches that visitor's namespace.

## Files

- `lib/types.ts` — the TypeScript contracts (not redefined here, only imported).
- `lib/api.ts` — the API client; mock/live switch, SSE parsing for `/chat`.
- `lib/visitor.ts`, `lib/format.ts` — visitor id and ₹/date formatting helpers.
- `components/` — `Badge`, `ForecastChart` (inline SVG, no chart library), `GapCard`,
  `CounterfactualBars`, `GuardrailList`, `ApprovePanel`, `ChatPanel`, `TracePanel`,
  `PolicyEditor`, `HealthStrip`.
- `mocks/*.json` — fixtures for every route, consistent with `lib/types.ts`.
- `tests/e2e/*.spec.ts` — Playwright: the landing golden path and the phone golden path.
