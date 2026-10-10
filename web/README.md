# Taal — web (`web/`)

Next.js 15 App Router front end for Taal: the judge-mode landing, Play Desk, phone
capture view, Meena chat, and Outcomes. See `docs/DECISIONS.md` §5.6, §9, §10 and §11a for
the product spec this implements.

## Run it

```bash
cd web
npm ci --no-audit --no-fund
npm run dev            # http://localhost:3000 dev server; mock mode via .env.local
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
message text: "offers" returns the bundle offer (English only: the recorded chips play carries no Kannada copy; with the best-before date),
"Cola Zero" returns the out-of-stock substitution list; a reply in Kannada carries an `english_gloss` line shown under the bubble, "STOP" returns the opt-out
confirmation, anything else returns a generic prompt.

## Commands

```bash
npm run typecheck   # tsc --noEmit
npm run build       # next build
npm test            # Playwright, mock mode (NEXT_PUBLIC_TAAL_MOCK=1), port 3100
npm run test:headed # same, headed
```

Playwright uses the Chromium under `PLAYWRIGHT_BROWSERS_PATH` when it is set, otherwise its own
`chromium` channel. Run one dev server at a time: `npm test` starts `next dev` on port 3100 (it reuses
one that is already there), and two dev servers in `web/` share one `.next` folder.

### The two test suites

| Suite | Config | Needs | What it proves |
|---|---|---|---|
| Mock mode | `playwright.config.ts`, specs in `tests/e2e/` | nothing but `npm ci` | Every route, state and error path against `web/mocks/`; node-level specs for the pure functions (`lib/*`); axe, 360 px overflow, keyboard and reduced-motion checks. Projects: `desktop` (everything except `*-phone.spec.ts`) and `mobile` (Pixel 7: `*-phone`, `phone`, `feedback`). |
| Live | `playwright.live.config.ts`, specs in `tests/live/` | the real API and web app | The persona walkthroughs against the stub model backend (no cloud calls). |

Run the live suite exactly the way CI does (`.github/workflows/verify.yml`, job `live-test`), from the
repo root:

```bash
uv sync --group dev
make generate                      # seeded tenant, Sense, demo plays, flagship prior update -> .local/data
make api                           # uvicorn on :8080 (the Makefile pins TAAL_NOW, TAAL_MODEL_BACKEND=stub, TAAL_TENANT_CONFIG)
make web                           # next dev on :3000, mock mode OFF (talks to :8080)
make live-test                     # cd web && npx playwright test -c playwright.live.config.ts
```

The Makefile exports `TAAL_NOW=2026-09-12T03:30:00Z`: without it the API uses today's date, every play
window has ended and `POST /approve` answers 409. Live screenshots land in `eval/runs/screens`, traces in
`eval/runs/live-results` (both git-ignored).

## Pages

| Route | What it shows |
|---|---|
| `/` | The decision landing. One hero sentence, the demo-date chip, the LIVE / REPLAY / SYNTHETIC legend, then "Run the 60-second beat": one `PlayCard` in hero mode for `HERO_GAP_ID`, with the choreographed Approve. Beside it the Meena chat. Under 768 px the landing is the `DecisionFeed`: the top three decisions as cards with a sticky Approve bar. Footer: what is simulated, tenant size, health, and Reset demo data (last in the tab order, behind a confirm). |
| `/desk` | Play Desk: inbox ranked by rupees at stake and the selected play as a `PlayCard` in detail mode (holdout slider, editable rationale), the guardrail attempts trace (recorded run replayed at 4x, or **Plan live**), copy tabs and the policy editor. Under 768 px it is two screens, the inbox and one play, with the play in the URL hash so the browser Back button works. |
| `/phone` | Priya's capture flow: node, sample pallet photos (plus an experimental own upload), the intake table with confirm questions, the gap's `PlayCard`, Approve, execution checklist. |
| `/chat` | The Meena chat full page: customer picker, Kannada bubbles with a collapsible English line, "English fallback" label, optimistic bubble with Retry, STOP demo button. |
| `/outcomes` | Summary card first (the visitor's measured result, or the empty state with Run Measure), then the portfolio projection (SYNTHETIC), the seeded worked example, and the measured-plays table (cards under 768 px). |
| `/feedback`, `/feedback/results` | The practitioner survey and its results. |
| `/dev/play-card` | A gallery of the `PlayCard` states for development. |

## Persona bar, guided tour and fast-forward (the cut-line items)

- **Persona bar** (`components/PersonaBar.tsx`, `lib/personas.ts`): a thin row under the nav on the five
  screens saying who the screen is for (Arjun, demand planner on `/`, `/desk`, `/outcomes`; Priya, node
  manager on `/phone`; Meena, customer on `/chat`) with an inline-SVG initial avatar (decorative) and "View as"
  chips for the other two. Chips are plain links ("View as Priya, node manager"), 44 px tall; under 480 px the
  role text goes and "This screen is for" becomes "For". No images.
- **Guided tour** (`components/Tour.tsx`, `lib/tour.ts`): four coach-marks on the landing, anchored with
  `data-tour` attributes (`why-now`, `proof`, `approve`, `step-offer`), shown once per visitor
  (`localStorage` key `taal_tour:<visitor id>`, cleared by Reset demo data), started 0.5 s after the decision
  card is on screen, with "Skip tour", Esc, a focus trap only while open, focus returned on close, a polite live
  region per step, and a "Take the tour" button in the legend row. The popover is placed from the anchor and
  Approve rectangles (`placePopover`) and flips so it never intersects an Approve button or its decision row.
  **Phones** get the same card, tighter, placed by the same rule (above the sticky Approve bar); there is no
  separate bottom sheet. Kill switch: `localStorage.taal_tour_off = "1"` stops the automatic start (the link
  still works); both Playwright configs set it so the first-visit popover does not sit on unrelated flows, and
  `tests/e2e/tour.spec.ts` starts from an empty storage state instead.
- **Fast-forward one day** (`components/FastForwardPanel.tsx`, `lib/fastForward.ts`): on Outcomes, when the
  visitor has approved a play and none of their plays is measured, a SYNTHETIC panel runs three honest steps with
  real elapsed times, using existing client calls only: `getDemoCustomers` (the treated persona), `sendChat` with
  the `add:<sku>` quick reply (the order), `postMeasure`. The result lands in the summary card (Inconclusive badge
  when the range crosses zero, the difference in points, "1 treated customer ordered", and the sentence that one
  order proves nothing). A chat failure shows the ErrorCard with Retry and leaves nothing placed; an order placed
  with a failed Measure says so and offers only Run Measure. Single use per play (`fastForwarded` in the progress
  crumbs, cleared by Reset). In mock mode `lib/mockMeasure.ts` stands in for the sandbox (a mocked order, then a
  computed SYNTHETIC measured row). The stepper's Measure step now turns done only for a measured row of a play
  the visitor approved.

## The LIVE / REPLAY convention

Every panel that shows a result carries a `Badge` (`components/Badge.tsx`):

- **LIVE** — a real call was made (or, in mock mode, a call whose *real* counterpart is a
  live call: Approve and Chat).
- **REPLAY** — a recorded/golden result (Sense's gaps, the Planner's pre-proposed play, the
  event trace, past plays in the inbox).
- **REAL PILOT** / **SYNTHETIC** — the data-provenance label used on Outcomes rows.

In mock mode every panel is labelled REPLAY except Approve and Chat, which are labelled
LIVE (mock) — the same convention the running app uses once wired to the real backend,
where a failed call shows an `ErrorCard` (below) rather than a blank panel.

## Errors, timeouts and the recorded fallback

Every real request goes through `apiFetch` in `lib/api.ts`: one `AbortController` per request and
a per-endpoint timeout (10 s by default; `/approve` 60 s; `/plan` and `/rerun` 100 s; `/chat` and
`/capture` 20 s; `/measure` 30 s). A failure is a typed `ApiError` (`lib/apiError.ts`) whose `kind` is
`network`, `timeout`, `http`, `model_unavailable` (503 with `{"error":"model_unavailable"}`),
`conflict` (409), `not_found` (404) or `rate_limited` (429), with `status`, `retryAfterSeconds` and
`endpoint`. `components/ErrorCard.tsx` renders it in plain language with Retry and, where the app
ships a copy of the data (`lib/recorded.ts`: gaps, plays, one trace, outcomes), "Show recorded
result", labelled REPLAY. For `model_unavailable` the Retry button waits out the seconds the server
asked for.

### Mock faults and delays

Two `localStorage` keys steer mock mode (both are no-ops in a production build):
`taal_mock_fault` makes a route fail (below) and `taal_mock_delay` slows one down so a short state
stays on screen: `localStorage.setItem("taal_mock_delay", JSON.stringify({ "/approve": 4000, "/chat": 9000 }))`.
Without a delay every mocked route answers in 150 to 900 ms (`/approve` about 1 s, `/chat` the fixture's
own latency, at most 1.6 s per envelope).

### Making a mocked route fail

In mock mode (`NEXT_PUBLIC_TAAL_MOCK=1`) set `localStorage.taal_mock_fault` before the page loads:

```js
localStorage.setItem("taal_mock_fault", JSON.stringify({
  "/chat": { kind: "model_unavailable", retry_after_s: 30, times: 1 },
  "/capture": { kind: "model_unavailable" },
  "/gaps": { kind: "network" },
}));
```

Keys are path prefixes (longest wins); `kind` is any `ApiError` kind; `times` limits how many calls
fail. `window.__taalMockCalls[path]` counts calls per route. In tests use `injectMockFaults` and
`mockCalls` from `tests/e2e/helpers.ts`. A production build contains none of this
(`lib/mockData.ts` and `lib/mockFaults.ts` sit behind an inline `process.env.NEXT_PUBLIC_TAAL_MOCK`
check that `next.config.ts` always defines, so the fixtures are dropped from the client bundle).

`tests/e2e/blocked-origin.spec.ts` aims the real request wrapper at an address nothing listens on
(`forceLiveApi` in `tests/e2e/helpers.ts` sets `localStorage.taal_force_live` and `taal_api_url`,
honoured only in a mock-flag build) to prove the card shows within 10 s, and answers a fake API with
`page.route` for the 503, 409, 404 and hang cases.

## Plain language

`lib/labels.ts` maps the demo tenant's ids to names (`label("sku", "SKU-MASALA-CHIPS-200G")` is
"Masala Chips 200G"; an unknown id comes back unchanged). Raw ids, JSON and traces sit inside the
`Details` disclosure ("Show technical details"). `lib/guardrails.ts` reads each guardrail's detail
text and shows three honest states (passed, not applicable, pending) with a one-line summary.
`lib/impact.ts` (`playImpact`) is the one place the "Recovered vs doing nothing" figure and the
comparison with a blanket markdown are computed.

## The hero gap: `HERO_GAP_ID`

`lib/hero.ts` exports `HERO_GAP_ID` (today `gap_tea_ds04`, the Darjeeling Tea transfer play). It is the
only place the hero is named: the landing beat, the feed order and the stepper's Approve tick all read
it, and every sentence on the card comes from the gap and play the API returns, so changing the constant
(or re-recording the flagship) rewrites every screen. Specs that depend on it say so; the live specs
expect Tea with its Rs 35,020 at stake.

## Per-visitor sandbox

`lib/visitor.ts` keeps a random id in `localStorage` (`taal_visitor`); `lib/api.ts` sends it
as the `X-Taal-Visitor` header on every request (with `credentials: "include"`) so the
backend can scope state per visitor in its local/overlay store (Firestore in the deployed
service holds practitioner feedback only). "Reset demo data" on the landing page only
touches that visitor's namespace.

## Component map

```
app/                      routes (App Router); each route has a layout.tsx that sets its <title>
components/
  PlayCard                the one decision card, three modes: hero (landing, phone view), detail (Desk),
                          feed (DecisionFeed). Renders the figure, bars, plain sentences, guardrail
                          summary, Details, and owns an ApprovePanel.
  ApprovePanel            the Approve button and its state machine (idle, submitting, animating, settled,
                          error, already-approved). Uses ApproveSteps (honest timer), ApproveToast,
                          ForecastChart, RecoveredFigure (count-up), MeenaPreview (the real /chat reply).
  DecisionFeed            under 768 px: ranks gaps, renders PlayCards in feed mode, sticky Approve bar,
                          "Next decision". It only composes PlayCard; it has no Approve logic of its own.
  PersonaBar, Tour, FastForwardPanel   the cut-line items (see "Persona bar, guided tour and fast-forward")
  Stepper                 the five-step nav (Spot, Plan, Approve, Offer, Measure) in the top bar; reads
                          lib/progressStore (crumbs in localStorage + /plays + /outcomes), never the server.
  ChatPanel / MeenaPreview  chat bubbles; the preview is the Approve result's phone frame.
  ErrorCard, Details, Badge, StateLegend, Skeleton, InfoNote   shared building blocks.
  GapCard, CounterfactualBars, GuardrailList, TracePanel, PolicyEditor, HealthStrip   Desk pieces.
lib/                      pure logic and the API client (api.ts, apiError.ts, labels.ts, impact.ts,
                          format.ts, lang.ts, progress*.ts, mock*.ts, recorded.ts)
mocks/*.json              fixtures for every route (mock mode only)
tests/e2e, tests/live     see "The two test suites"
```

How they relate: a route picks a `PlayCard` mode and gives it a play and a gap. `PlayCard` shows the
decision and mounts `ApprovePanel`; when Approve succeeds `ApprovePanel` calls `recordApproved`, which
moves the `Stepper`, and the `MeenaPreview` it shows is one real `/chat` call. `DecisionFeed` is
`PlayCard` times three plus the phone chrome.

## CSS convention

New components use CSS Modules (`Foo.module.css` next to `Foo.tsx`). The older global classes in
`app/globals.css` (`.card`, `.chat-msg`, `.outcomes-table`, `.chat-panel__stop`, ...) stay because the
specs select on them; when a component moves to a module it keeps those class names, and
`data-testid` values are never renamed without updating the specs. Colours, spacing and type come from
the tokens on `:root` (light) with a dark override under `prefers-color-scheme: dark`; never a hard-coded
hex in a component. An unclassed `<button>` gets the secondary look from `button:not([class])`, so giving
a button a module class means styling it fully in that module.

## Design rules

The rules the screens follow (one figure, plain language, state words with icons, 44 px targets,
tokens, motion only at Approve, contrast and focus) are in `coordination/ui-ux/design_spec.md`, with the
copy deck and the interaction-state table in sections 8 and 9. The three-person test kit is
`coordination/ui-ux/usability_test.md`. In short:

- One headline figure, "Recovered vs doing nothing", from `playImpact()`, never typed.
- Ids, JSON and commands live inside `Details`. Rupees through `inr`, dates through `relativeDate` or
  `dayMonth`, never ISO text or "Rs" in UI-generated copy.
- Every state is an icon plus a word, never colour alone. Every loader times out into an `ErrorCard`.
- Every interactive element has a visible focus ring; `prefers-reduced-motion` and forced colours are
  respected; the skip link is the first tab stop on every route.

## Files

- `lib/types.ts` — the TypeScript contracts (imported, not redefined).
- `lib/api.ts` — the API client; `apiFetch`, mock/live switch, SSE parsing for `/chat`.
- `lib/apiError.ts`, `lib/errorCopy.ts`, `lib/mockData.ts`, `lib/mockFaults.ts`, `lib/recorded.ts` — see "Errors" above.
- `lib/personas.ts`, `lib/tour.ts`, `lib/fastForward.ts`, `lib/mockMeasure.ts` — the cut-line items' pure logic.
- `lib/impact.ts`, `lib/labels.ts`, `lib/guardrails.ts`, `lib/lang.ts` — the figure, the names, the checks, the language detection.
- `lib/visitor.ts`, `lib/format.ts` — visitor id; rupee, date, duration and percentage-point formats.
- `mocks/*.json` — fixtures for every route, consistent with `lib/types.ts`.
