# Taal — Build Guide v3.1 for the AI Builder Cup 2026 (Retail & Commerce)

**Positioning line:** "Every forecast tells a retailer what will be thrown away. Taal is the agent that sells it first: legally, to the right people, at the right margin, with a holdout to prove it."

This is a build guide for a 3–4 person team using Antigravity, AI Studio and Vertex AI (Gemini Enterprise Agent Platform). No implementation code. It is written so a teammate can build each component without asking questions: schemas, tool contracts, wire protocols, screens, evaluation design, deployment, week-by-week tasks per role, demo script, deck, submission checklist. Every factual claim is tagged [Certain], [Likely] or [Guessing]. This session could not open aibuildercup.com, hack2skill.com, YouTube or Google docs directly; competition facts come from official-page search snippets plus the text you pasted from the portal.

---

## 0. Verdict: can this win?

Three independent reviews were run on the previous version (v2): a CEO/jury review, an outside principal-engineer review, and a contrarian brief whose job was to beat the idea with a better one. They converged.

| Reviewer | Verdict on v2 | Recommendation |
|---|---|---|
| CEO / Google Cloud MD jury lens | Shortlist-likely (top 10–15% of the Retail track); finale-winner-plausible only after changes | Improvise Taal (confidence ~70%): one pipe, a real pilot with ≥30 consented customers, the FSSAI legal-deadline reframe, TimesFM-3 headline if it lands, rebuild the video |
| Outside engineer / hackathon mentor | Strong product spec, not yet a build spec; four missing contracts; full scope ≈ 750 person-hours vs ≈ 440 available | Add the contracts; cut to one pipe; hard week-2 gate; fix two wrong product claims |
| Contrarian strategist | v2 scores ≈ 64/100 at shortlist, ≈ 66 at finale; finale probability 30–40%; grand prize 2–3% [Guessing, calibrated] | Build "Taal Live" (confidence ~60%): merchant-side voice + vision intake, "approve → forecast moves" as the live beat, demote the customer chat, cut WhatsApp/Memory Bank/contribution analysis; projected ≈ 74–77/100 |

**Honest answer to "can we win the whole cup with this?"** As v2 was written: no. It would likely shortlist and would likely not win the room, because its wow was a table, its impact was simulated, and its scope would not have shipped. The v3 below is the improvised version all three reviewers pointed at. It is a plausible finale contender, in the same band as the two higher-variance alternatives (a merchant-side UCP agent, a live-stream co-host), with a lower failure surface and a better fit to your team's edge (e-commerce ops and CRM). The winner is still decided by execution: a working live URL, a real number, and a rehearsed demo. [Guessing on all probabilities]

**Alternatives considered and parked** (details in §16): Dwaar, a seller-side agent that makes any JAPAC merchant buyable by AI shopping agents over UCP/AP2 (higher innovation ceiling, weaker "who pays now" story, protocol risk); Seedha, a Gemini Live co-host for live-stream selling (highest ceiling, highest live-demo risk, poor fit to team skills). Both live on the roadmap slide.

### What changed from v2 (the seven improvisations)
1. **The deadline is legal, not printed.** FSSAI requires food delivered online to have at least 30% of shelf life or 45 days remaining at delivery [Certain: FSSAI advisory to e-commerce FBOs, Nov/Dec 2024]. A pack that "expires in 20 days" is unsellable online in 6. That "online sell-by" date is invisible in every forecasting tool and is the opening 10 seconds of the video. It also reads as compliance + revenue, the register of past cross-theme winners. [Likely on the register mattering]
2. **The wow is physical and merchant-side.** The store or node manager photographs a pallet; Gemini reads best-before dates and counts facings; she asks by voice what to do; the gap card and the play appear, spoken back. The planner inbox is the second screen.
3. **The live beat is "approve → the forecast moves."** An approved play becomes a known-future covariate; the forecast chart and the write-off number change on screen. Demand shaping made literal, with no simulated customers. (`ARIMA_PLUS_XREG` now; TimesFM-3 multivariate the day it lands in BigQuery, which Google says is imminent [Likely].)
4. **Impact is a real pilot, not a simulator.** ≥30 consented real people on web chat for one week, real holdout, real (small) orders. The homemade responder module is gone. Agent Simulation (Agent Platform) is used only to pre-flight the customer agent's behaviour across simulated shopper personas, never to estimate lift.
5. **One pipe.** `AI.FORECAST` + `ARIMA_PLUS_XREG` (needed for beat 3), estimator, gate, Planner loop, Play Desk, minimal chat, Measure, Looker Studio. Cut now, not later: WhatsApp, Memory Bank, contribution analysis, separate outlet app, Pro toggle, Croston path, second text language, UCP hook, Conversational Analytics.
6. **The customer chat is a cameo.** Minimal web chat with six tools, used for the pilot and 20 seconds of the video. Gemini Enterprise for CX and Meta Business Agent are named as delivery channels on the roadmap slide, not competed with.
7. **The CEO's number is on the last card:** net margin recovered per rupee of discount given, versus holdout, on the target lot.
8. **Cross-theme framing without changing theme.** The theme stays Retail & Commerce (your expertise, and the speaker's retail examples match Taal directly). But the top-50 shortlist is cross-theme, so the impact slide carries two lines that other themes' judges recognise: a demand-and-supply line (the speaker's manufacturing framing) and a **food-waste line in kilograms and CO2-equivalent** computed from units of the target lot saved from write-off (the speaker's sustainability enthusiasm, and the "Most Impactful" award). Measured in the Measure job from `units_target_lot × pack weight × a cited emissions factor`, labelled as an estimate.

---

## 0.1 Scoring to the top (v3.1): what 95 would take, and what is actually reachable

Two more reviews were run on v3: a rubric-maximiser that scored v3 as three judge archetypes, and a simulation of the async shortlisting reviewer's twelve minutes. Their answer to "how do we score 95 and get to ~95% shortlist probability" is the same as mine, and it is not what you asked for.

**The honest ceiling.** v3 as written scores ≈ 78–79 expected (spread 74–84 across plausible panels). With every change below executed, the expected score is **84–88**, a favourable panel reaches **~90–92**, an unfavourable one ~80. **95 is not a plannable target**: it needs every archetype to give 9+/10 on Innovation and Impact to a B2B operations tool judged asynchronously, and Technical Merit has a soft ceiling around 36–38/40 for anything without production traffic. **A 95% shortlist probability is not plannable either**: panel composition, whether a given judge opens the live URL at all, product timing (TimesFM-3, Kannada voice quality, model retirements) and the 4 Oct vs 18 Oct deadline conflict are outside your control. What is plannable: an entry that no archetype can score below ~80, that is impossible to reject on requirements, and that a reviewer retells at the end of the day. [Guessing on all numbers, calibrated across five independent reviews]

**Where v3 loses points (audit, summed against a ~90 entry)**
| # | Loss | Points | Fix |
|---|---|---|---|
| 1 | Scalability & sustainability sub-criterion is a README paragraph, not evidence | −3 to −4 (Tech) | `docs/scale.md` with measured Sense/Planner throughput, Gemini tokens per play from the billing export, extrapolation to a 20,000-SKU retailer, tenant model, the three-CSV ingestion contract; one deck slide; one 8-second video card |
| 2 | Evaluation table is a list of intentions | −2 to −3 (Tech) | Commit the evalset (~50 gaps), raw `adk eval` output, Agent Simulation report, vision accuracy table on 30 staged photos, guardrail test count; filled table on one slide and in the README, run at freeze |
| 3 | The FSSAI rule is stated more confidently than its "30 percent or 45 days" wording supports | −1 to −2 (Impact, credibility) | `sellby_rule` is a versioned policy parameter shown on the gap card; README and deck say "we implement the stricter reading; retailers set their own"; cite the advisory date and URL |
| 4 | The pilot (≥30 people, small holdout) cannot produce a defensible number | −2 to −3 (Impact) | 50–60 participants, 40–50% holdout, one pre-registered metric (response rate on the target lot), `docs/pilot.md` with recruitment method and consent text, a concrete mechanism for real orders (a friend's shop's real near-expiry stock, or a micro-lot bought and resold at cost, named); frame the pilot as proof the measurement loop runs on real humans, and let the economics come from the counterfactual card on the seeded tenant, labelled |
| 5 | Video: eight beats in 170 s; the strongest Gen AI proof sits at 125 s where skimmers have left | −2 to −3 (Innovation/UX/Impact for the skimmer) | The shot list in §9: ≤ 2:40, five beats, burned-in text that carries the meaning muted at 1.5x, chart beat by 1:04–1:22, policy beat by 2:00 |
| 6 | Three headline claims, therefore none | −1 to −2 (Innovation) | One sentence said twice: "an invisible legal deadline becomes a forecast covariate the merchant approves by voice"; the estimator and the domain-agnostic schema become supporting lines |
| 7 | Gen AI reads as one agent plus vision | −1 to −2 (Tech) | The "what Gemini decides / what it is not allowed to decide" slide with one trace screenshot per row; README table mapping each Gemini call to the problem and what breaks without it |
| 8 | Judge-mode concurrency: judges approve the same play and reset each other | −1 to −2 (UX/Tech) | Per-visitor sandbox (Firestore namespace keyed by session cookie, cloned from the snapshot on first load), or idempotent approve with an "already approved at HH:MM" banner and a reset scoped to the visitor |
| 9 | The root URL's first 60 seconds are unspecified | −1 to −2 (everything, if the judge bounces) | The landing spec in §5.6 |
| 10 | Vision beat is fragile on a judge's own photo | −1 | Three preloaded pallet photos; own upload labelled experimental |
| 11 | Unverified model IDs on slides | 0 to −2 | Never print a model ID that is not in the running config; verify in Model Garden day 1 |
| 12 | TimesFM-3 temptation | 0 if resisted, −2 if it eats week 3 | Build the live beat on `ARIMA_PLUS_XREG`; add TimesFM-3 only as a baseline line if it lands before freeze |
| 13 | Impact numbers are top-down extrapolations | −1 | A bottom-up per-node number from the seeded tenant in the first 20 s, labelled; ask interviewees for a real per-store rupee figure |
| 14 | Deadline was ambiguous in third-party listings | resolved | The organiser stated 18 Oct in the explainer session. Plan a complete submission by 9–11 Oct; use the last week for hardening and the five changes above; re-verify the portal weekly anyway |
| 15 | "Documentation" may be a separate upload field | 0 to −1 | Export a 6–10 page PDF from README + docs |
| 16 | Antigravity evidence thin | 0 to −1 (and the "Best use of Google Cloud AI tools" special) | Three walkthrough artifacts linked with captions; one screenshot on the architecture slide |
| 17 | Consent and privacy is one section | 0 to −1 | Add a half-page threat model: what leaves the tenant, where photos live and for how long, what the Customer Agent can and cannot see |

**Five highest points-per-hour changes, in order**
1. Judge-mode first 60 seconds (root page with guided tour, "Run the 60-second beat" button, "Chat as Meena" pre-filled, health strip, preloaded photos, per-visitor sandbox; README quick-start card as the first 15 lines): 8–12 h, +3 to +5 across all criteria.
2. Scalability evidence (`docs/scale.md`, slide, video card): 6–8 h, +3 to +4.
3. Video re-cut to five beats with burned-in text and state labels: 8–10 h, +3 to +4.
4. Evaluation evidence committed with numbers: 8–10 h, +2 to +3.
5. Pilot redesign and framing: 10–15 h, +2 to +3.
Runner-up: the "what Gemini decides / is not allowed to decide" slide with trace screenshots: 3–4 h, +1 to +2.

**Shortlist insurance (make rejection impossible)**
Live URL: **min-instances=0 (scale-to-zero), accepting cold starts** on all three services through the judging window (team decision, overriding the min-instances=1 plan below: idle cost is not worth paying for the whole window) -- weekly smoke test with an alert, `/health` page, first paint under 4 s tested from a second machine on mobile data, golden-run fallbacks with visible badges. Video: ≤ 2:45 by the platform counter, public/unlisted on YouTube plus a Drive backup, tested in an incognito window, "Retail & Commerce" and the retailer persona in the first 10 s. Repo: public from day 1, Apache-2.0, `DATA_LICENSES.md`, no third-party raw data, no employer code, CI green, commit history that looks like four weeks of work by several people, no 200 MB clone. Deck: PDF and Slides link, ≤ 12 slides, rubric order, a final rubric-map slide with weights. Documentation PDF never empty. Eligibility: written confirmation per member (non-student, 21+, JAPAC), team locked on the portal by 11 Oct. Google stack: architecture slide names each product; Gemini only via Vertex in a fresh project. Deadline: complete by 3 Oct.

**The three things a reviewer must be able to retell at dinner**, delivered in this order on the first 10 s of video, slide 2, the judge-mode landing and the README top fold, with the same rupee figure on all four: a fact they did not know ("food sold online in India must have 30% of shelf life left, so a 20-day pack is unsellable online in 6, and no forecasting tool knows that"); a picture ("she photographed the pallet, asked in Kannada, the manager clicked approve and the forecast line bent on screen"); a number with integrity ("real people, a holdout, the CI shown, and one play they refused to measure").

---

## 1. Competition facts (compressed, verified)

| Item | Fact | Confidence |
|---|---|---|
| Eligibility | Working professionals, entrepreneurs, startups; students disqualify the whole team even after shortlisting; 21+; all members JAPAC-based (India qualifies by convention); free | Certain / Likely on 21+ and India |
| Team | 2–4 during build; solo registration then join; 2 travel; one team, one theme, one submission | Certain |
| Dates | Registration approvals are batched (a "waitlisted" status is normal; watch the registered email); team of 2–4 finalised by **11 Oct**; build and submit by **18 Oct** (stated by the organiser in the explainer session, which settles the 4 Oct vs 18 Oct conflict); shortlist **7 Nov**; finale Singapore **4 Dec 2026**. Plan a complete submission by 9–11 Oct and use the remaining week for hardening | Certain (explainer transcript) |
| Shortlist size | **Top 50 teams** across all six themes are shortlisted and flown to Singapore (2 members per team); teams handle their own visas | Certain (explainer transcript) |
| Tech | Gemini/Gemma or approved agentic platforms (Agent Platform, Antigravity, AI Studio); deploy on Cloud Run or Firebase; fresh project only | Certain |
| Portal's suggested tech (your paste) | Gemini on Vertex AI, Vertex AI Search / Agent Search, BigQuery, BigQuery AI, Cloud Run, Cloud Storage, AlloyDB or Cloud SQL, Looker | Certain |
| Submission | (1) **Documentation** as PPT or PDF: what the solution does, its impact, how it aligns to the chosen theme and which problem inside the theme it addresses, how the prototype addresses that problem, a user guide, and **longevity: how it would run in production, scalability, feasibility**; (2) a functional prototype deployed on Cloud Run or Firebase (any Google Cloud runtime) that demonstrates the capabilities the documentation claims; (3) a demo video with voiceover on YouTube, Vimeo or a public Drive link; (4) a public GitHub repo showing the work was done in the hackathon window; everything **in English** | Certain (explainer transcript) |
| Judging | Technical Merit & Gen AI 40%; Problem Alignment & Impact 25%; Innovation & Creativity 25%; UX 10%; same rubric all themes; scoring round → shortlist → live finale | Certain |
| Prizes | 10,000 / 7,000 / 5,000; four 2,000 specials: Best use of Google Cloud AI tools, Most Impactful Solution, **Jury Choice** (the organiser said "jury choice", not "social choice"), Best UI/UX; cross-theme. The organiser's own hint: "integrate a few more Google Cloud AI tools and services" for the tools award | Certain on the transcript; Likely on the award name |
| IP | Remains fully with the team | Certain (explainer transcript) |
| Credits | No evidence; assume $300 trial + Always Free; Gemini via AI Studio is not covered by the trial since March 2026, so route Gemini through Vertex | Certain on the AI Studio exclusion |

**What the Google DevRel speaker said that bears on this build (explainer session):** Retail entries should show engaging customer experiences, understanding and serving the customer, operational efficiency, seamless checkout and return processes, both physical stores and e-commerce, hyper-personalisation, conversational experiences, and "inventory management, demand planning based on the season, the festivals" [Certain]. Technical merit is "not just send a prompt to the AI and get a response"; innovation means "don't redo a solution that has already been built" and "experiences that will wow us, that people would want as an actual application"; UX is ease of use, "not just a flashy UI". He recommended starting with **Gemini 3.8 Flash**, ADK, Cloud Run, Firestore (Cloud SQL for relational needs, BigQuery for analytics on large or public datasets), a **progressive architecture** ("build with the simplest components, deploy, then evolve"), and to **have evals** that validate outputs. Gemma is welcome "if you have an interesting use case for a local model"; Antigravity is named as an "AI harness" to build with; AI Studio for UIs; Agent Platform vector search as an out-of-the-box RAG option. Technical sessions and another AMA will follow; support is support@hack2skill.com. Every one of these maps to a choice already in this guide; the one to underline is the documentation's **longevity section** (production path, scalability, feasibility), which most teams treat as an afterthought and which §18 and `docs/scale.md` answer with numbers.

---

## 2. Concept v3

### 2.1 Persona
**Kutumb Mart**: a regional grocery and snacks retailer in Bengaluru with its own app, 10 micro-fulfilment nodes (its own dark stores) and 6 physical outlets. Brands on Blinkit/Zepto do not see dark-store stock or reach those customers, so the persona must own its fulfilment. [Likely] No pet products anywhere (zero overlap with your employer).

Users: **Priya, node manager** (phone, voice, camera; the hero of the video); **Arjun, demand planner** (Play Desk on a laptop; approves); **Meena, customer** (web chat; the cameo and the pilot).

### 2.2 The loop
| Stage | Runs | Where | Output |
|---|---|---|---|
| 0. Capture (new) | Any time | Priya's phone (web, camera + mic) → Vision intake → `inventory_batches` | Batch rows with best-before dates and counts, read from a photo, confirmed by voice |
| 1. Sense | Nightly + on demand | BigQuery | `forecasts` (baseline + play-aware), `gaps` with ₹ at stake and the **online sell-by** deadline |
| 2. Plan | Nightly; re-run per gap | ADK Planner Agent on Cloud Run | `plays` proposed, with audience, mechanic, copy, estimator output, guardrails, rationale, trace |
| 3. Approve | Human | Play Desk, or by voice on the phone | `plays.status`; assignments with holdout; **forecast re-run with the play as covariate** (the live beat) |
| 4. Engage | Continuous | Minimal Customer Agent, web chat | offers delivered, orders with `play_id` |
| 5. Measure | Nightly | BigQuery | `play_outcomes` treated vs holdout; estimator priors updated; "unmeasured" enforced |

### 2.3 Gap types and the legal deadline
- `online_sellby_breach`: units projected unsold by the **online sell-by date**. The FSSAI advisory wording is "30 percent or 45 days before expiry at the time of delivery" [Certain on the wording], which is ambiguous; Taal implements `sellby_rule` as a **versioned policy parameter** (default: the stricter reading, expiry − max(30% of shelf life, 45 days)), shows the rule on the gap card, and states in the README and deck that retailers set their own reading. After that date the lot can only move through physical outlets or be written off.
- `expiry_writeoff`: units projected unsold by physical expiry.
- `stockout_risk`: forecast over lead time exceeds on-hand + inbound.
- `rebalance`: at risk at node A, short at node B.
- `slow_mover`: velocity below category median for 21 days.

### 2.4 The "play" (first-class object; JSON Schema is the single source of truth for BigQuery DDL, Pydantic models and TypeScript types)

```
Play
  play_id: string            gap_id: string           created_at: timestamp
  objective: enum [clear_online_sellby, clear_expiry, prevent_stockout, rebalance, revive_slow_mover]
  target: { sku, node_ids[], batch_ids[], units, deadline_date, deadline_type: enum[online_sellby, expiry, lead_time] }
  mechanic: enum [bundle, usual_order_addon, substitution, preorder, subscription_nudge, coupon, outlet_markdown, transfer_plus_nudge]
  mechanic_params: { discount_pct?, bundle_sku?, bundle_price?, transfer_to_node?, preorder_eta_date?, markdown_pct? }
  audience: { segment_ids[], filters: { min_affinity, recency_days, node_radius_km }, purpose: "marketing", size_before_consent, size_after_consent }
  channel: enum [web_chat, app_push, outlet]
  window: { start: timestamp, end: timestamp }          // approve time → deadline; Measure joins on this
  copy: { language_set[], variants[]: { segment_id, language, text, disclosure_included }, copy_status: enum[pending, generated, validated, rejected] }
  expected_outcome: { units, margin_inr, waste_avoided_inr, discount_cost_inr, ci_low, ci_high, prior_n, measured_n, estimator_version }
  counterfactuals: { do_nothing_inr, blanket_markdown_inr, blanket_markdown_pct }
  holdout: { fraction: number ≥ 0.05, seed: string, min_treated_n: int }
  guardrails: [{ rule, passed: bool, detail }]
  rationale: string                                     // editable by the merchant
  citations: [{ type: enum[gap, estimator, outcome, policy, forecast], ref }]   // cite_or_drop resolves these
  alternatives: [{ mechanic, mechanic_params, expected_outcome }]
  policy_version: string
  trace_ref: string                                     // events/{run_id}
  status: enum [proposed, approved, modified, rejected, running, measured, unmeasured]
  approved_by?, approved_at?, edits?: [{ field, from, to, at }]
```

### 2.5 Guardrails (deterministic Python, unit-tested; no LLM touches money or the right to act)
`margin_floor` (net margin after discount ≥ category floor; policy stored as prose for the Planner and as numbers for the gate), `frequency_cap` (≤ N plays per customer per 7 days), `consent_required` (audience filtered by the consent table for purpose `marketing` on the channel), `sellby_disclosure` (any near-deadline mechanic states best-before in the copy), `subscription_protect` (active subscribers of the SKU excluded from discount plays on it), `no_cannibalise_stockout` (no push of a SKU with a stockout gap at the same node), `holdout_required` (fraction ≥ 0.05 and `min_treated_n` set), `cite_or_drop` (every number in the rationale must appear in `citations` and resolve; otherwise the Planner revises). Three-person team: make `cite_or_drop` a soft eval metric and drop `no_cannibalise_stockout`.

### 2.6 Consent
`consent(customer_id, channel, purpose, source, ts, withdrawn_at)`. The gate reads it; the Customer Agent writes `withdrawn_at` on "STOP"; the Play Desk shows the audience shrinking after the consent filter. One README section and one slide: consent-native by design (DPDP Rules 2025 / PDPA). [Likely on rule details]

### 2.7 Why Gen AI is load-bearing (the 40% answer, in one breath)
Gemini reads a pallet photo into batch rows with dates; understands a manager's spoken Kannada question and answers with tool calls; reasons over prose policy, complaint text, festival context and past outcomes to choose a play a rules engine cannot express, and revises it when a guardrail fails; writes the vernacular copy. What is deliberately not LLM: the forecast, every rupee (estimator), the guardrails, holdout assignment, the measurement. "The rules decide what is allowed; Gemini decides what to do; the estimator owns the numbers."

### 2.8 Answers to the three objections
- "Marketing automation with a forecast": the objective function is supply-side per lot × node × deadline; the counterfactual card shows do-nothing vs blanket markdown vs targeted play; plays are emitted as audience + copy that a retailer's existing CRM can send (Taal is a decision layer, not a fourth channel).
- "Meta Business Agent is free": Taal initiates from a gap; Meta answers. Taal's chat is grounded in node stock, sell-by dates and substitutions; Meta's is catalogue-aware. Name Meta and Gemini CX as channels.
- "Where is the Gen AI": the policy-change beat (edit one sentence of policy, the Planner's choice and rationale change) and the guardrail self-revision in the trace.

---

## 3. Data

### 3.1 Licence decision (day 1, not week 4)
Raw third-party data never enters the repo; only download and transform scripts. The Dunnhumby "Complete Journey" dataset (real households, baskets, coupon campaigns) is the preferred grounding for basket affinity, segments and coupon-response priors, but its licence appears to require permission for public use [Likely]. Email dunnhumby on day 1; if no written permission by end of week 1, fall back to a fully synthetic layer with disclosure, and use a Kaggle competition series (Favorita or M5) only for the forecast backtest under its terms. A `DATA_LICENSES.md` lists every source and its terms.

### 3.2 Layers
- **Public grounding (if licensed):** households → `customers`, baskets → `affinity`, coupon campaigns → `estimator_priors`.
- **Synthetic Indian layer (seeded generator, in repo):** ~300 SKUs (Indian grocery/snacks; category, pack, unit cost, list price, margin floor, shelf-life days, `is_food`), 10 nodes + 6 outlets with coordinates, `inventory_batches` with expiry and derived `online_sellby_date`, inbound POs, festival calendar (Diwali, Pongal, Ugadi), consent records, daily sales series built by disaggregating weekly totals with a day-of-week profile then to nodes by fixed shares plus noise (state this rule), and planted situations: a lot 6 days from online sell-by at node DS-07; a Diwali stockout risk at two nodes; a slow mover at outlets; a premium tea gap for the policy beat.
- **Real pilot:** 50–60 consented testers as Kutumb Mart customers on web chat for one week; 40–50% holdout; one pre-registered metric (response rate on the target lot); a concrete mechanism for real orders (a friend's shop's real near-expiry stock, or a micro-lot bought and resold at cost, named in `docs/pilot.md` with recruitment method and consent text). Framed as proof that the measurement loop runs end-to-end on real humans; the economic headline comes from the counterfactual card on the seeded tenant, labelled. Labelled real everywhere; the same rupee figure on every surface.
- **What is simulated:** stated in a box on the evaluation slide and in the README.

### 3.3 BigQuery schema (dataset `taal`, region decided day 1: check BigQuery ML/TimesFM and Agent Engine availability in asia-south1; fallback `us` or asia-southeast1 [Likely that some features are US/EU-first])

| Table | Columns (key) | Notes |
|---|---|---|
| `products` | sku, name, category, pack_size, unit_cost, list_price, margin_floor_pct, shelf_life_days, is_food | partition none; small |
| `nodes` | node_id, type, lat, lng, lead_time_days, cluster_id | |
| `inventory_batches` | sku, node_id, batch_id, qty_on_hand, expiry_date, **online_sellby_date**, received_at, source (enum: system, photo) | photo-captured rows carry `capture_ref` |
| `inbound` | sku, node_id, qty, eta | |
| `sales_daily` | date, sku, node_id, units, revenue, on_promo | partitioned by date, clustered by sku |
| `future_regressors` | date, sku, cluster_id, on_promo, is_festival | built nightly from approved plays + festival calendar; input to `ARIMA_PLUS_XREG` forecasts |
| `orders`, `order_lines` | order_id, customer_id, node_id, sku, qty, price, discount, play_id, ts | |
| `customers` | customer_id, home_node_id, language, rfm_tier, segment_id, subscription_skus[] | |
| `affinity` | customer_id, sku, score | |
| `segments` | segment_id, name (human-readable), k, features | KMEANS k = 6 |
| `consent` | as §2.6 | |
| `forecasts` | run_id, sku, node_id, cluster_id, date, p10, p50, p90, model (enum: timesfm, arima_xreg), includes_plays (bool) | |
| `gaps` | gap_id, run_id, type, sku, node_id, batch_id, units_at_risk, deadline_date, deadline_type, rupees_at_stake, evidence (STRUCT: on_hand, projected_sellthrough, forecast_run_id, sellby_rule) | |
| `plays` | play_id, gap_id, status, … , play_json (JSON) | JSON column mirrors the schema in §2.4 |
| `play_assignments` | play_id, customer_id, arm (treated/holdout), assigned_at | |
| `conversations`, `messages` | session_id, customer_id, channel, role, text, tool_calls (JSON), citations (JSON), latency_ms, ts | |
| `play_outcomes` | play_id, arm, customers, responders, units_target_lot, revenue, margin, discount_cost, waste_avoided, lift, ci_low, ci_high, status (measured/unmeasured), computed_at | |
| `estimator_priors` | mechanic, category, segment_id, alpha, beta, n_measured, updated_at | |
| `eval_forecast`, `eval_planner`, `eval_copy` | see §12 | |

Firestore (serving reads; never the system of record): `stock/{node}/{sku}` (qty, nearest online_sellby, nearest expiry), `customers/{id}` (language, home node, arm per play, pending offers), `offers/{customer_id}` (pending proactive deliveries), `plays/{id}` (status snapshot), `events/{run_id}/{seq}` (agent trace, see §10), `demo/` (golden runs and reset snapshot).

### 3.4 Estimator (deterministic; owns every expected number)
Response rate per (mechanic, category, segment) ~ Beta(alpha, beta). Prior from public coupon-redemption rates by category and household segment if licensed, otherwise a weak, disclosed prior (low pseudo-count). Each measured play updates alpha/beta with treated responders and non-responders. `expected units = size_after_consent × E[rate] × avg_qty_per_responder` (avg_qty from `order_lines` history for the SKU); `margin_inr = units × (price − discount − unit_cost)`; `discount_cost_inr = units × discount`; `waste_avoided_inr = min(units, units_at_risk) × unit_cost`; bundles priced as (bundle_price − sum of unit costs); transfers as (avoided write-off − transfer cost per unit × units). CI from the Beta quantiles. Counterfactuals: do-nothing = units_at_risk × unit_cost; blanket markdown = (baseline forecast units × markdown × price) + remaining write-off, using the planner-set markdown_pct. The Play card shows prior n / measured n. Never India-calibrated claims; the prior is weak and overwritten by measurement.

---

## 4. Architecture

### 4.1 Services

| Service | Product | Notes |
|---|---|---|
| `taal-sense` | Cloud Run Job + Cloud Scheduler (nightly) | forecasts → gaps → segments → copy for approved plays → Firestore mirror |
| `taal-agents` | ADK (Python) on Cloud Run, min-instances=0 (team decision, see §4.5) | Planner Agent, Customer Agent, Vision intake endpoint, Live voice session endpoint, deterministic tools, in-process MCP order mock, approve/rerun/reset HTTP API, SSE for trace and chat |
| `taal-web` | Next.js on Cloud Run | Priya's phone view (camera, mic, gap card, approve), Play Desk, customer web chat, Outcomes, judge mode, replay |
| Data | BigQuery (system of record), Firestore (serving), Cloud Storage (photos, golden runs, reset snapshot) | |
| Sessions | Agent Platform Sessions (`VertexAiSessionService`) | requires an Agent Engine instance created in week 1 to obtain the engine ID; no Memory Bank in v3 |
| Insights | Looker Studio public embed on BigQuery (owner's credentials, data freshness 12 h) | [Certain on embed mechanics] |
| Observability | ADK OpenTelemetry → Cloud Trace; Cloud Logging | |
| Eval | `adk eval` evalsets; Agent Simulation for the Customer Agent pre-flight; BigQuery eval tables | |

### 4.2 Data flow
Photo/voice capture → `inventory_batches` (source=photo) → Sense: `AI.FORECAST` (TimesFM 2.5, `id_cols` = [sku, cluster_id]; no holiday argument exists on this function [Likely]; festival effects come from `ARIMA_PLUS_XREG`) and `ML.FORECAST` on `ARIMA_PLUS_XREG` with `future_regressors` (holiday_region 'IN', `on_promo`, `is_festival`) → node roll-down by trailing 28-day share → `gaps` with ₹ and deadline → Planner (tools) → `plays` proposed → Approve (voice or Play Desk) → assignments (Firestore sync, BigQuery async) → **forecast re-run for the affected series with the play in `future_regressors`** → chart updates → Customer Agent delivers and answers → `orders` with `play_id` → Measure → `play_outcomes`, priors → Looker Studio.

### 4.3 Latency budget
Customer Agent turn under 3 s p50 / 6 s p95 (Flash streaming; stock from Firestore; substitutes precomputed; no per-turn memory calls). Vision intake under 8 s per photo. Voice turn under 2 s to first audio (Live API; record the beat for the video regardless). Planner per gap 20–60 s, nightly or streamed on re-run. Approve → forecast re-run for one series under 15 s (single-series `ML.FORECAST` on a pre-trained model; pre-train models nightly so approve only calls `ML.FORECAST` with the updated regressor table). Sense job: minutes, never live.

### 4.4 Pinning and environment (week 1, owner B)
`google-adk` pinned to an exact 2.x release (2.0 broke 1.x APIs; tutorials are mostly 1.x [Certain]); model IDs pinned in config, never defaults (ADK changed its default model and `gemini-2.5-flash` shuts down 16 Oct 2026 [Certain]); candidate IDs: `gemini-3.8-flash` for text/vision/planner [Certain that it launched 2 Sept 2026 per one reviewer; verify in Model Garden], `gemini-3.1-flash-live-preview` for voice [Likely]; a fallback text model ID in config; Agent Engine instance created and its ID in env; region decision recorded; Vertex quota increases requested; Secret Manager for all keys; budget alerts at $50/$100/$200; `uv.lock` committed.

### 4.5 Cost caps
Gemini only via Vertex. Flash everywhere. No Vertex AI Vector Search endpoints, no AlloyDB, no Looker Core [Certain on cost traps]. **Superseded 21 Sep 2026: the team decided min-instances=0 (scale-to-zero) for the whole judging window instead of min-instances=1** -- request-based billing (CPU throttled outside requests) already applies by default and was confirmed live on both public services; idle cost for min-instances=1 across the full window was judged not worth it against the cold-start cost (see eval/evaluation.md for measured cold-start numbers). `infra/min_instances.sh on` remains available for a specific demo day if ever wanted. Copy generation only for approved plays.

---

## 5. Component specs

### 5.1 Capture: Vision intake and voice (owner B, with C for the phone view)
- **Vision intake endpoint:** input = photo (Cloud Storage ref), node_id; Gemini image understanding with a strict output schema: `[{ sku_guess, confidence, best_before_date, date_confidence, facings_count, count_confidence, crop_ref }]`; rows with any confidence < 0.7 become one confirmation question each ("Is this Masala Chips 200 g, best before 28 Sept?"); confirmed rows are written to `inventory_batches` with `source=photo`, `online_sellby_date` derived. Filming rule for the demo: dates fill at least a quarter of the frame; two-pass (find the label region, then read a crop) if single-pass reads are unreliable in week-1 tests.
- **Voice:** Gemini Live session from the phone view; system instruction scoped to Kutumb Mart ops; tools = `get_gaps(node_id)`, `explain_play(play_id)`, `approve_play(play_id)`, `ask_confirmation`; language Kannada with English fallback (verify Kannada quality in AI Studio in week 1; if weak, use Hindi or English for the live beat and keep Kannada copy only [Likely that language coverage varies]). The voice beat is recorded for the video; live at the finale only if week-3 rehearsals pass on hotel-grade wifi.

### 5.2 Sense (owner D)
1. `AI.FORECAST` baseline per sku × cluster, horizon 28, TimesFM 2.5 (verify option names) [Likely].
2. `ARIMA_PLUS_XREG` models per sku × cluster trained nightly with `holiday_region='IN'`, regressors `on_promo`, `is_festival`; forecasts read `future_regressors`; `ML.EXPLAIN_FORECAST` decomposition stored for the Play card. Three-person team: keep this (it powers the live beat) and drop the TimesFM baseline instead if one model must go.
3. Node roll-down by trailing 28-day share; intermittent series (≥ 50% zero days) use a simple average-demand rule, labelled.
4. Gaps per §2.3; `rupees_at_stake` per §3.4; `evidence` struct filled.
5. Segments: KMEANS k = 6 on RFM + category share; human-readable names written by hand in `segments.name`; `affinity` scores per customer × sku from co-purchase.
6. Substitutes: `AI.GENERATE_EMBEDDING` on product text → `VECTOR_SEARCH` top-5 same-category candidates per SKU into Firestore; stock filtering happens at chat time.
7. Copy: `AI.GENERATE_TABLE` over a Vertex-connected Gemini Flash remote model, only for approved plays, output schema `copy_text STRING, disclosure_included BOOL, reason STRING`, numbers passed as constants with "copy exactly"; validator rejects mismatched discounts or missing best-before; one automatic regeneration; templated fallback.
8. Firestore mirror; backtest (rolling origin, 8 weeks, MAPE and bias by tier and model).

### 5.3 Planner Agent (owner B)
- `LlmAgent` inside a `LoopAgent` (max 3) that exits when the gate tool writes `guardrails_all_passed = true` into session state, else escalates with the failure detail injected verbatim into the next turn. Fan-out over gaps in the nightly job via a bounded worker pool (Cloud Tasks queue is the scale story for the deck).
- Inputs: gap row; policy text (versioned); product context (attributes, complaint summary, festival calendar); past outcomes for similar plays.
- Tool contracts (all deterministic; inputs/outputs as JSON):
  - `get_gap(gap_id) → Gap`
  - `get_candidate_audiences(sku, node_ids[], objective) → [{ segment_id, name, size_before_consent, size_after_consent, mean_affinity }]`
  - `estimate_outcome(play_draft) → expected_outcome + counterfactuals` (§3.4)
  - `check_guardrails(play_draft) → [{ rule, passed, detail }], all_passed`
  - `get_past_plays(sku | category, mechanic) → [{ play_id, mechanic_params, expected, measured, status }]`
  - `propose_play(play) → play_id` (validates against the JSON Schema; writes `plays`, `events`)
- Output: Play JSON via structured output. Demonstrated behaviours: chooses `transfer_plus_nudge` when the estimator shows a markdown gives margin away; changes mechanic when policy text changes; cites estimator numbers; lists alternatives.
- Prompts live in `agents/planner/prompts/*.md` with a changelog; iterated in AI Studio, run through Vertex.

### 5.4 Approve and assignment (owner B)
Approve is an HTTP action on `taal-agents` (from the Play Desk or the voice tool). It: sets status; writes `play_assignments` with arm = treated if `FARM_FINGERPRINT(customer_id || seed) % 100 ≥ holdout × 100` else holdout, to Firestore synchronously and BigQuery asynchronously; writes `offers/{customer_id}` for treated customers; inserts the play into `future_regressors`; triggers the single-series forecast re-run and returns the new p50 path and updated write-off for the chart. Holdout customers receive nothing, including when they ask "any offers?" (`apply_offer` and proactive delivery both check arm).

### 5.5 Customer Agent, minimal (owner B; chat UI owner C)
- `LlmAgent`, Flash, streaming; session key `customer_id:web`; `VertexAiSessionService`.
- Six tools: `get_customer_context(customer_id) → { home_node, language, pending_offers[], arms{} }`, `get_stock(sku, node_id) → { qty, online_sellby, expiry }` (Firestore), `find_substitutes(sku, node_id) → [{ sku, name, qty }]` (precomputed candidates filtered by stock now), `apply_offer(play_id, customer_id) → ok | refused(reason)` (arm, consent, frequency cap, margin floor), `place_order(lines[]) → order_id` (in-process FastMCP mock via `McpToolset`; writes `orders` with `play_id`), `record_stop(customer_id)`.
- Proactive delivery: the first turn of a session reads `pending_offers` and delivers the play in the customer's language with the best-before disclosure.
- Wire protocol (one envelope for chat, used by web now and WhatsApp later): `{ session_id, role, text, buttons?: [{id,label}] (≤3), list?: { title, rows: [{id,title,desc}] } (≤10), citations: [{type: stock|play|forecast, ref}], latency_ms }` over one SSE endpoint.
- Pre-flight: Agent Simulation runs ~200 simulated shopper personas against the agent per release to check guardrail compliance (no coupon stacking, no offer to holdout, STOP honoured), reported as a pass rate. It never produces a lift number. [Certain that Agent Simulation exists; Likely it fits this use]

### 5.6 Play Desk and phone view (owner C)
Phone view (Priya): camera capture → confirmation questions → gap card (sku, node, units, ₹ at stake, **online sell-by countdown** with the rule shown, expiry) → play summary → Approve → forecast chart that moves. Play Desk (Arjun): inbox ranked by ₹; play card (target, mechanic, audience before/after consent, copy with language toggle, expected outcome with CI and prior/measured n, counterfactual bars, guardrails, alternatives, editable rationale, holdout control, a "Why this play?" drawer showing the rejected alternatives and the estimator numbers that killed them); trace panel (live or replay from the same event log, `invocation_id` visible); policy editor (versioned) with a "Change policy → re-plan" button; Outcomes (per play treated vs holdout, units of the lot, waste avoided, margin, discount cost, the CEO number; "unmeasured" when below `min_treated_n`; Looker link that opens without login).

**Judge-mode landing (root URL), the first 60 seconds:**
- Top band, one line: "Taal judge mode: seeded tenant Kutumb Mart. Nothing you do here persists beyond your session." with a **Reset demo data** button scoped to the visitor.
- Hero left: **"Run the 60-second beat"**. One click opens the chips gap card pre-filled (DS-07, 340 units, ₹9,200, online sell-by in 6 days, rule shown), shows the pre-proposed play with a replay badge ("Planner run recorded 2 Oct 22:14 IST"), and stops at a large **Approve**. Approve is live: assignment, re-forecast, the chart moves, the write-off counts down, a chip reads "ML.FORECAST · live · 11.3 s · run id …". Nothing else is needed to score the entry.
- Hero right: **"Chat as Meena"**, pre-filled first message ("Any offers today?") and a suggested chip ("Do you have Cola Zero?"); live badge with latency chip; STOP works.
- Below the fold, three cards with LIVE / REPLAY badges: Play Desk (live reads), Phone view (with "use a sample pallet photo": three preloaded photos; own upload labelled experimental), Outcomes ("REAL PILOT DATA, computed 3 Oct").
- Footer: video, deck, repo, the what-is-simulated box, tenant size ("300 SKUs, 10 nodes, 4,000 customers; last Sense run N min at HH:MM"), and a health strip from `/health` (BigQuery, Firestore, Vertex, Sessions, with timestamps).
- Per-visitor sandbox: Firestore namespace keyed by a session cookie, cloned from the Cloud Storage snapshot on first load; approve is idempotent; reset touches only the visitor's namespace; BigQuery history is never touched. Fail-safe: if a live call errors, the panel shows the golden result with a visible "showing recorded result (live call failed)" badge, never a blank.
- English default with a language toggle; no login wall; first paint under 4 s when warm -- **min-instances=0 in the actual deployment (see §4.5), so the judge's first request pays a cold start instead.**

### 5.7 Measure (owner D)
Join `orders` to `play_assignments` within `window`; per arm compute customers, responders (order line with `play_id`, or the target SKU at the target node inside the window), units of the target lot, revenue, margin, discount cost, waste avoided; lift = treated rate − holdout rate with a normal-approximation CI; status = measured only if treated ≥ `min_treated_n` (default 20), else unmeasured; update `estimator_priors`; `future_regressors` already carries the play. No contribution analysis in v3.

### 5.8 Looker Studio (owner D)
Public embed with owner's credentials, "anyone with the link", embed enabled, data freshness 12 h [Certain]. Cards: plays by status; treated vs holdout per play; waste avoided; margin preserved vs blanket markdown; **net margin recovered per ₹ discounted**; stockouts prevented; MAPE by tier; consent coverage; unmeasured count. The Outcomes screen reads a `play_outcomes` snapshot from Firestore and links to the full report.

### 5.9 Stylist specialist (owner B; chat UI owner C)
A second specialist on the same chat runtime, not a second headline: §0.1's warning about "three
headline claims, therefore none" applies here too, so this is framed as a second application of
chat-as-demand-signal (§2.3's `unmet_demand` gap type), not a new pillar of the entry.

**Why a second specialist.** Kutumb Mart's chat already turns an unanswered ask into a structured
demand signal (`customer_requests` → `unmet_demand`). A styling ask ("what goes with this kurta?")
carries garment, colour and occasion — richer signal than a stock lookup, and a second, real use of
the same mechanism. Retailers and the small apparel manufacturers that supply them get a live read
on what customers are actually asking for in a store, by garment, colour and occasion — a count of
asks, not a forecast, and labelled SYNTHETIC on this demo tenant.

**Catalogue.** A separate seeded apparel line, `apparel_products` (~350 SKUs across ~45 garment
types: ethnic and western wear, footwear, accessories) and `apparel_stock` (per size, dark stores
only), generated on its own RNG stream (`data/generator/apparel.py`) so the grocery generator's
300-SKU invariants and the sell-by/gap pipeline never see it and are never touched by it.

**`LlmAgent`, Flash, six tools**, ADK app `taal_stylist` (never the same session as the grocery
agent's `taal_customer`, even for the same `customer_id:web`): `get_style_context(customer_id)` →
home node, language, recent asks, confirmed style profile if any; `find_apparel(query, node_id)` →
in-stock matches by garment/colour/occasion words; `describe_item(sku)` → catalogue attributes;
`suggest_pairings(anchor, node_id, occasion?)` → up to 10 in-stock pairings for a named item or a
free-text description; `set_style_profile` / `forget_style_profile` → the skin-tone profile below;
`apply_offer` / `place_order` → checkout through the same MCP order mock the grocery Customer
Agent uses (`agents/mcp_orders`), so an assortment_gap play (below) is actually redeemable, not
just proposed. `jobs/measure/run.py`'s `products` lookup is `agents/gate/store.py::load_catalogue`
(grocery `products` merged with `apparel_products`, apparel rows defaulting to
`category="apparel"`), the one shared change that let checkout, approve and Measure all resolve
an apparel sku without a second pipeline.

**What Gemini decides vs what is deterministic.** Exactly the same split as §2.7: the model chooses
how to talk about a look and which pairing to lead with; the hue wheel, every pairing score and
reason, the in-stock filter, the demand-signal write and the trend aggregation are plain Python
(`agents/stylist/colour.py`, `tools.py`, `jobs/sense/trends.py`) — no LLM scores a pairing or
resolves a colour family. A free-text garment description ("a mustard yellow kurta") is parsed by
a deterministic vocabulary lookup (`parse.py`) over the same tables the catalogue was built from;
an unrecognised colour degrades to neutral-only suggestions rather than failing.

**Photo input.** A garment photo or a selfie is read into attributes before the agent runs, in the
vision-intake pattern (`agents/capture/vision.py`): a stub returns recorded attributes for staged
fixtures in CI, Gemini with a strict output schema in `vertex` mode. `colour_family` is always
resolved deterministically from the read colour, never a model output.

**Skin-tone profile, opt-in and confirmed.** A customer can declare an undertone/depth by button or
share a selfie; either way the coarse read (`warm`/`cool`/`neutral` undertone, `light`/`medium`/
`deep` depth) is repeated back and only saved after the customer confirms it — `set_style_profile`
is never called straight off a photo read. The selfie image itself is never stored anywhere;
`customer_style_profile` holds only the two enums, gated by a `consent(purpose="style_profile")`
row alongside the existing `marketing` purpose, deletable on request ("forget my skin tone") the
same way STOP withdraws marketing consent. The profile nudges a pairing's score by at most ±0.10 for
items worn near the face, and never removes a candidate; it never reaches `style_requests` or
`style_trends` — those tables have no skin-tone column, by schema, not just by convention.

**Demand signal.** `style_requests` mirrors `customer_requests` for fashion: every ask, hit or
miss, is recorded deterministically by the tools, never an LLM decision. `jobs/sense/trends.py`
aggregates it into `style_trends` (by node, garment type, colour family, occasion), kept only at or
above `style_trends_min_asks` within `style_trends_lookback_days`; `GET /trends` serves it and
`POST /trends/recompute` runs it on demand (the `POST /measure` pattern), shown on a SYNTHETIC-
labelled web panel.

**assortment_gap: the demand-driven counterpart to `rebalance` (built).** `jobs/sense/gaps.py`
resolves real, unfulfilled `style_requests` for a (node, garment_type, colour_family) into a
named gap when the catalogue has a matching sku that some OTHER node in the same cluster actually
carries -- `rebalance`'s own surplus-at-A/need-at-B shape, sourced from a customer ask instead of
the forecast. The Planner drafts a `transfer_plus_nudge` play for it with objective `rebalance`;
`get_candidate_audiences` reaches the play's real askers directly via the gap's
`evidence.requesting_customer_ids` (the grocery `affinity` table has no coverage for an apparel
sku, so the audience tool's usual affinity fallback would otherwise be empty). A demand signal
with no matching catalogue sku, or no in-cluster supply, stays an assortment/buying decision
outside what a play can fix -- left in `style_requests`/`style_trends` for a merchandising
review, exactly the principle already documented for a `customer_requests` `no_match` (§2.3) --
never forced into a gap. This is the whole point of the second specialist made concrete: the same
gap → guardrail-gated play → holdout → measured-outcome loop this project built for food waste,
proven on a second, unrelated retail vertical without a second pipeline.

**Phase 2, not built here:** feeding `style_trends` into `future_regressors` as a per-category
covariate, once real ask volume exists to justify it; a `specialist` column on `conversations`.

---

## 6. Building with Antigravity, AI Studio, Vertex AI
- **Antigravity:** scaffold the repo and the Next.js screens from §5.6; use the Cloud Run MCP server for builds and deploys; keep at least three walkthrough artifacts and reference them in the README (approved platform evidence).
- **AI Studio:** iterate the Planner and Customer prompts, the Play schema, the Vision intake schema and the Kannada voice test on real gap rows; export into the ADK configs; no AI Studio keys at runtime.
- **Vertex AI / Agent Platform:** Model Garden for IDs; Sessions; Agent Simulation and `adk eval`; Cloud Trace.
- **BigQuery Studio:** Sense and Measure SQL; backtests.
- **Looker Studio:** §5.8.

---

## 7. Repository layout

```
taal/
  README.md              # judge quick-start card at the top (URL, what to click in 90 s, replay vs live), architecture diagram (Mermaid, week 1),
                         # setup, one-command demo/deploy, data disclosure + what-is-simulated box, consent/privacy + threat model, how-Gen-AI-is-used table,
                         # Antigravity/AI Studio/Vertex evidence, cost sheet (demo scale and 100k customers), scale story (Cloud Tasks fan-out)
  LICENSE (Apache-2.0)   DATA_LICENSES.md
  docs/                  # DECISIONS.md (this guide, incl. parked alternatives and "what we tried that did not work"), schemas/play.schema.json, openapi.yaml (approve, rerun, chat SSE, reset, capture),
                         # architecture.png (+ Mermaid source collapsed), scale.md (measured throughput, tokens/play, extrapolation, tenant model, three-CSV contract, "what breaks first"),
                         # pilot.md (pre-registered metric, holdout, recruitment, consent text, anonymised outcomes), screenshots/, demo-script.md, deck outline, interview notes,
                         # documentation.pdf (6-10 pages exported from README + docs for the portal's documentation field), 60-second repo walkthrough video link
  Makefile               # make demo (seed + run against the demo tenant), make deploy (gcloud scripts), make eval
  .env.example
  data/generator/        # seeded synthetic Indian layer, exact BigQuery schema; sample slice checked in so judges can run without third-party data
  data/public/           # download + transform scripts only; never raw data
  data/bigquery/         # DDL, views, Sense/Measure SQL, backtest queries
  agents/planner/        # agent, tools, prompts/*.md (changelog), evalsets
  agents/customer/       # agent, six tools, wire envelope, simulation config
  agents/capture/        # vision intake schema + endpoint; live voice session config
  agents/gate/           # guardrails + estimator, pytest
  agents/mcp_orders/     # in-process FastMCP order mock
  web/                   # Next.js: phone view, Play Desk, chat, Outcomes, judge mode, replay
  jobs/sense/  jobs/measure/
  tests/                 # unit, property, sql assertions, scripted conversations, playwright (judge mode), golden path e2e
  harness/               # builder + reviewer prompts, checklists per component (§17.3), spec-review GitHub Action, STATUS.md generator
  fixtures/              # golden plays (valid + mutated), conversations, staged photos, outcome fixtures, demo snapshot
  infra/                 # gcloud shell scripts (services, scheduler, IAM matrix per service account, budgets, min-instances toggle), GitHub Actions (pytest on gate/estimator, schema validation on golden plays)
  eval/                  # backtests, planner evalset results, simulation pass rates, golden runs, latency logs, billing export
```

---

**Commit and authorship conventions.** Commits are authored under team members' own git identities with plain engineering messages (imperative subject ≤ 72 characters, what and why, a body when the change needs one). No assistant attribution trailers, session links, tool names or model identifiers appear in commit messages, PR descriptions, code comments, docs or the deck; AI-assisted building is expected by the organiser (Antigravity is named as an approved harness) and is described once, factually, in the README's tooling section. No backdating, history rewriting to hide work, or synthetic activity: the history must be a truthful record of work inside the hackathon window, because that is what the public-repo requirement exists to show.

## 7a. Competitor scan (12 Sept 2026)
No team has published a concept, repo or "we are building" post for this hackathon that search engines have indexed yet [Certain for today]. Proxy: retail entries that placed in the last three Google-judged hackathons. Buyer-facing personalisation suites (V-Commerce Studio, Cartmate), a delightful small end-to-end agent (cart-to-kitchen, GKE grand prize), a seller-side generative listing tool (ArtisanGully, Gen AI Exchange 2025 grand winner), an ops analytics briefing with rupee impact that stops at "recommend" ("How Did I?", Rapid Agent 2026), a hierarchical fraud agent behind a human gate (Vigil AI), and a sustainability-flavoured shopping assistant (CO2-Aware) [Certain on the entries]. Expected field this year: 30–50 shopping assistants, 20–40 analytics-plus-forecast dashboards, 10–20 inventory or waste agents [Guessing]. Taal beats the first two groups on the speaker's own criteria; inside the third group it is decided by the legal-deadline gap, the approve-to-forecast beat and the measured pilot. Name "How Did I?" and Gemini Enterprise for CX on the competitor slide as the nearest cousins and state the exceedance in one line each. Re-run this scan on 1 Oct and 15 Oct (LinkedIn, X, GitHub, Hack2skill community) and adjust the competitor slide.

## 8. Team plan (4 people, near full-time; full v3.1 scope; hard gate at end of week 2)

**Capacity and budget (your decision: 35–45 productive hours per person per week).** 4 × 40 × 4 = **640 hours**, with Antigravity-assisted coding at a realistic 1.2–1.4x giving **770–900 effective hours** [Guessing on the multiplier]. Full v3.1 scope is estimated at **750–800 hours**, so it fits with little slack; the week-2 gate is the checkpoint that tells you whether the estimate is holding. Hour estimates per component (from the outside engineer's v2 figures, adjusted for v3.1):

| Block | Hours | Owner |
|---|---|---|
| Harness (§17): schemas, DDL, generator determinism, CI, `make verify`, builder/reviewer prompts and checklists, `spec-review` job, `STATUS.md`, Playwright suite, golden path | 50–60 | D (build), B (prompts, checklists) |
| Data: synthetic layer, public-data transform, BigQuery load, `DATA_LICENSES.md` | 40 | D, A |
| Sense: `AI.FORECAST` + `ARIMA_PLUS_XREG` + `future_regressors`, roll-down, gaps with ₹ and sell-by rule, segments, substitutes, copy, mirror, backtest | 70 | D |
| Estimator + gate + Play JSON Schema + types | 50 | B |
| Planner Agent + tools + revise loop + evalset | 60 | B |
| Approve, assignment, re-forecast beat | 20 | B, D |
| Customer Agent (six tools, MCP mock, sessions) + Agent Simulation pre-flight | 60 | B |
| Capture: vision intake (two-pass), voice session, on-device first pass | 45 | B |
| Web: phone view, Play Desk, chat UI + envelope, Outcomes, judge-mode landing with per-visitor sandbox, replay, Looker embed | 110 | C |
| Measure + priors + Looker Studio report + cost metrics + Cost Governor (§18) | 45 | D |
| Infra: Cloud Run ×3, Scheduler, Secret Manager, IAM matrix, budgets, deploy scripts, smoke tests | 30 | D |
| Pilot (recruit 50–60, consent, run, write-up) and interviews (4–6) | 40 | A |
| Video (shot list), deck (12 slides), README top fold, documentation PDF, `docs/scale.md`, `docs/pilot.md` | 50 | A, C |
| Integration, hotel-wifi rehearsal, bug budget | 40 | all |
| **Total** | **~710–760** | |

Rules that make the budget hold: the harness is built in week 1 before any feature (it is what removes the back-and-forth); every component lands through the builder/reviewer loop; the week-2 gate is binary; if the gate is missed by more than two days, apply the cut order in §15 immediately rather than compressing week 3.

Roles: **A (you)** domain, policy text, planted situations, priors, pilot recruitment and consent, interviews (4–6, quotes on slide 2), deck, video, demo narration. **B** ADK agents, tools, capture (vision + voice), approve/assignment, sessions, evalsets, simulation. **C** Next.js phone view, Play Desk, chat, Outcomes, judge mode, replay, Looker embed. **D** BigQuery Sense/Measure, forecasts and backtests, segments, copy generation, Firestore mirror, Looker Studio, infra, CI, cost.

| Week | Hard milestone | Notes |
|---|---|---|
| 1 (12–18 Sept) | Register; recruit to 4; written employer clearance; pilot retailer or friend network committed; Dunnhumby permission requested; region and model IDs pinned; Agent Engine instance; **harness first (§17): schemas, DDL, generator determinism, CI with `make verify`, Builder/Reviewer prompts and checklists, `spec-review` job, `STATUS.md`**; repo with diagram; synthetic layer loaded; `AI.FORECAST` and `ARIMA_PLUS_XREG` running; vision-read and Kannada-voice feasibility tests in AI Studio **before any video script is written** | If TimesFM-3 appears in BigQuery, switch the baseline and headline it. From here on, every component lands through the builder/reviewer loop and is done only when `make verify` is green |
| 2 (19–25 Sept) | **Gate:** one planted gap → Planner proposes → approve on the Play Desk → forecast chart moves → Meena's chat delivers the offer and places an order → order visible, all on the live URL | Nothing outside the one pipe starts before this passes |
| 3 (26 Sept–2 Oct) | Vision + voice capture on the phone view; policy-change beat; Measure job; Looker; evalsets; simulation pre-flight; **pilot runs all week** (≥30 people); **feature freeze 2 Oct** | Golden runs recorded at freeze |
| 4 (3–9 Oct) | Video from hybrid mode, deck, README, documentation PDF (with the longevity section), live URL in judge mode; the five points-per-hour changes from §0.1 in order (judge-mode landing, `docs/scale.md`, video re-cut to the §9 shot list, eval numbers committed, pilot write-up); **complete submission on the portal by 9–11 Oct** | Deadline is 18 Oct (organiser-confirmed); 11–18 Oct is hardening, the write-up, and a resubmission if the portal allows edits |
| After | Weekly live-URL smoke test to 4 Dec; **min-instances stays 0 (scale-to-zero decision, §4.5); `infra/min_instances.sh on` available if a specific demo day ever wants it**; finale rehearsal on replay, then live, then replay | |

Full scope is committed at 35–45 h/week. If capacity drops (a teammate leaves, hours fall to evenings-and-weekends), apply this day-one drop list: voice (keep vision), TimesFM baseline (keep XREG), Kannada beyond copy, gate to six rules, interviews to 4, Agent Simulation to a manual test script, Playwright breadth to the golden path only.

---

## 9. Demo (video under 3 minutes) and finale

**Video: shot list (target 2:40; every shot carries its meaning as burned-in text so it works muted at 1.5x; numbers are always text; Kannada always subtitled; four visually distinct "scrub magnets" at shots 1, 7, 9, 11)**

| # | Time | On screen | Burned-in text | Voiceover |
|---|---|---|---|---|
| 1 | 0:00–0:08 | Real chips pack on a real dark-store shelf, tight. Overlay "Expires in 20 days", then a second overlay slams under it: "Online sell-by: 6 days" | "India's food regulator: online food needs 30% shelf life left at delivery." then "20 days on the pack. 6 days to sell it online." | "This pack expires in twenty days. By law, it can only be sold online for six. Nobody's forecast knows that." |
| 2 | 0:08–0:14 | Black. Logo, one line. Small: "Retail & Commerce · Kutumb Mart, Bengaluru: 10 dark stores, 6 outlets" | "Taal sells what the forecast says you'll throw away." | "Taal is the agent that sells it first." |
| 3 | 0:14–0:32 | Phone view: Priya photographs the pallet; boxes on labels; table fills (SKU, best-before, count, confidence); one amber row → confirmation question → Yes | "Gemini reads the pallet: dates, counts, confidence." Lower-third: "Low-confidence rows are confirmed, never assumed." | "Priya runs node DS-07. She photographs the pallet. Gemini reads the dates and counts and asks about the one it isn't sure of." |
| 4 | 0:32–0:46 | Mic tap, Kannada question with English subtitle; gap card animates in: 340 units, ₹9,200 at risk, "Online sell-by: 6 days (rule: 30%/45 days)", "Expiry: 20 days"; one-line play with a "Hear it" waveform | Subtitle: "What do I do with the chips?" | Her Kannada, then: "Three hundred forty units, nine thousand two hundred rupees at risk, six days. The agent already has a play." |
| 5 | 0:46–1:00 | Play Desk, one card, tight; three counterfactual bars build | "Do nothing: ₹9,200 lost. Blanket 20% off: ₹6,100 given away. This play: ₹1,900 cost." Lower-third: "Every rupee comes from a deterministic estimator, not the model." | "The planner chose a bundle for 1,400 consented customers who already buy this category. Do nothing, blanket markdown, or this." |
| 6 | 1:00–1:04 | Trace panel, one line red then green | "Guardrail failed: margin floor. Planner revised. Passed." | (none) |
| 7 | 1:04–1:22 | **The beat.** Approve. Baseline p50 line, then the play-aware line lifts; write-off counts down; "holdout 10%" badge | "Approve → the play enters the forecast as a covariate." then "Projected write-off: ₹9,200 → ₹2,700." Small: "BigQuery ARIMA_PLUS_XREG re-forecast, 11 s, LIVE." | "Approve. The play becomes a known future regressor. The forecast moves. That is the demand being shaped, on screen, with a holdout so we can prove it." |
| 8 | 1:22–1:40 | Meena's chat: offer in Kannada with best-before line; "Cola Zero?"; out at her node, Cola Lite or pickup; order placed; "stock row cited" chip; "2.4 s" chip | "Offer delivered with the best-before date. Substitution grounded in her node's stock." | "Meena gets the offer in her language, date disclosed. She asks for something we're out of; the agent offers what's actually on her shelf." |
| 9 | 1:40–2:00 | Full-frame result card (treated vs holdout bars, one big number), then a pan across Outcomes with one row "unmeasured" | "REAL PILOT: 1 week, N consented people, real orders." then "₹X net margin recovered per ₹1 of discount, vs holdout (CI shown)." Small: "One play too small to measure is marked unmeasured. On purpose." | "We ran it with real people for a week. Here is the treated group against the holdout, and the number a CEO asks for." |
| 10 | 2:00–2:12 | Policy editor: one sentence changed; re-run; mechanic changes from markdown to transfer_plus_nudge; rationale changes | "Change one sentence of policy → the agent's choice changes." | "Edit the policy in plain language and the planner chooses differently. That is why an LLM is here, and why it never touches the numbers." |
| 11 | 2:12–2:28 | Architecture card: clean logo grid with numbered arrows matching the beats | "BigQuery AI (AI.FORECAST, ARIMA_PLUS_XREG, VECTOR_SEARCH, AI.GENERATE_TABLE) · ADK agents on Cloud Run · Gemini on Vertex · Agent Platform Sessions + Simulation · Looker Studio · built with Antigravity + AI Studio" | "Everything on Google Cloud. The rules decide what's allowed; Gemini decides what to do; the estimator owns the numbers." |
| 12 | 2:28–2:40 | Closing card | "We do not claim: India-calibrated lift, WhatsApp, or a rules-free agent." "Same play schema works for any perishable decision. Retail first because the customer has to say yes." URL, repo, team | "Try it at the link. Judge mode, no login, one button." |

Cut from v3: the BFSI/manufacturing side-by-side (one line on the closing card keeps it), the extended trace walkthrough, the roadmap list. Persistent LIVE / REPLAY / REAL PILOT / SYNTHETIC labels on every UI shot.

**Finale (assume 5 min demo + 5 min Q&A; confirm)**: A narrates and takes business questions, B drives and takes technical questions. Live: approve, the chart, chat via a QR code on screen so a judge can open Kutumb Mart chat on their own phone, one policy re-run. Cached with a visible timestamp: Sense, Plan, Measure. Replay bound to one key. Warm-up script 5 minutes before: health checks, one session turn, stock rows for the three demo SKUs, offers doc for Meena, reset. The one visual: the counterfactual bars with a fourth thinner "holdout" bar that the live refresh moves.

---

## 10. Event log and replay (the demo's safety net; owner B + C)
All ADK events (author, invocation_id, function_call, function_response, text, timestamp, ts_offset_ms) are persisted to Firestore `events/{run_id}/{seq}`. The trace panel takes `run_id` and a mode: live (subscribe) or replay (read snapshot, emit at original timing or 4×). Golden runs recorded at freeze: chips gap Planner run with the revision; tea gap before and after the policy change; Meena's conversation; a Measure output. Demo modes on the Play Desk: replay (root URL default), live, hybrid (replay Planner, live approve/chart/chat). No live beat depends on a BigQuery write landing.

---

## 11. Deck (ordered by the rubric; ≤ 12 slides; a skimming reviewer reads slide 1, slide 2 and the last slide in full and glances at anything with one diagram or one big number)

**Slide 1:** name; positioning line cut to ≤ 12 words ("The agent that sells what the forecast says you'll throw away"); "Retail & Commerce" tag; live URL + QR; one hero screenshot (the chart bending). No stock photo.

**Slide 2, the executive summary (four quadrants matching the four sliders; three thumbnails; one bold number; nothing under 14 pt):**
```
TAAL — Kutumb Mart, Bengaluru: 10 dark stores, 6 outlets                       live URL
"20 days on the pack. 6 days to sell it online."  (India's food regulator: 30% / 45-day rule)
------------------------------------------------------------------------------------------
PROBLEM & IMPACT (25%)                     | TECHNICAL MERIT & GEN AI (40%)
• Legal online sell-by is invisible to     | • BigQuery AI: AI.FORECAST + ARIMA_PLUS_XREG
  every forecast                           |   (approve → re-forecast in 11 s), VECTOR_SEARCH,
• Real pilot: N consented people, 1 week,  |   AI.GENERATE_TABLE
  real orders, 40–50% holdout              | • ADK Planner (LoopAgent + deterministic gate) +
• ₹X margin recovered per ₹1 discounted    |   Customer Agent on Cloud Run; Sessions; Simulation
  vs holdout (CI ±)                        | • Gemini: vision intake, Kannada voice, policy
• Consent-native (DPDP)                    |   reasoning, copy. NOT LLM: money, forecast,
                                           |   guardrails, holdout, measurement
------------------------------------------------------------------------------------------
INNOVATION (25%)                           | UX (10%)
• Approve → the forecast moves (the play   | [phone view] [Play Desk] [chat]   3 thumbnails
  is a covariate)                          | • Judge mode, no login, "Run the 60-second beat",
• Play object: audience + copy + estimator |   reset
  + guardrails + holdout, emitted to any   | • Live vs replay labelled on every panel
  CRM                                      |
• vs marketing automation / planning       |
  suites / Meta Business Agent: slide 7    |
------------------------------------------------------------------------------------------
REAL: pilot orders, forecasts, agents, guardrails.  SIMULATED: catalogue, sales history,
stock (seeded generator, disclosed).  Evaluation numbers: slide 9.
```

**Last slide:** the CEO number repeated; the what-is-real / what-is-simulated box; URL and repo; one-line roadmap. The reviewer scores with this slide open.

Full order:
1. Title (as above). 2. Executive summary (as above). 3. The legal deadline (advisory date and URL; "we implement the stricter reading, retailers set their own"), a bottom-up per-node number from the seeded tenant (labelled), quick-commerce shelf-life gates and take rates [Likely], 4–6 interview quotes with role and retailer type, each tied to a feature. 4. The loop and the play object. 5. Technical Merit: architecture diagram with request paths numbered to match the video beats; a latency table from logs (p50/p95 per path). 6. **"What Gemini decides / what it is not allowed to decide"**: two columns with one trace screenshot per left-column item (`estimate_outcome`, `check_guardrails` returning `passed:false`, `propose_play`). 7. Innovation: competitor table with one row per real product (a markdown-optimisation vendor, a planning suite, Gemini Enterprise for CX, Meta Business Agent, a partner demand-sensing agent) and one column "sees the online sell-by date?" that is No for all but Taal; the three objections in one line each. 8. Impact: counterfactual economics; "who pays and why now" (advisory date, quick-commerce growth, buyer persona = category or supply-chain head, price anchor = share of waste avoided); adoption path (decision layer that emits plays to the existing CRM; three-CSV ingestion contract); consent slide with the STOP flow. 9. Evaluation: "numbers we can defend", ≤ 8 rows from §12, filled at freeze. 10. **Scalability & sustainability**: four boxes (throughput measured and extrapolated; unit economics with tokens per play from the billing export; onboarding in a day; sustainability: Flash-only, no idle endpoints, nightly batch, consent-native), plus the multi-tenant line (tenant_id on every table, per-tenant policy, IAM per service account). 11. UX: one slide per persona with the single job and the single action; judge-mode URL. 12. Last slide (as above). A final rubric-map footer with the weights on each section slide.

---

## 11a. README top fold (what a reviewer sees without scrolling)
1. Title line + one-sentence positioning + badges (CI green, Apache-2.0, "Cloud Run: healthy").
2. **Judge quick-start card** in a box: live URL · "click Run the 60-second beat, then Approve" · video link (2:40) · deck link · two lines on what is live vs replay · reset note. This is the first 15 lines of the file.
3. One row of three captioned screenshots (phone gap card; chart bending after approve; Outcomes with the CEO number).
4. `docs/architecture.png`, with the Mermaid source in a collapsed details block.
5. **"How Gen AI is used"** table: component · model ID (as in the running config) · what it decides · what is deliberately not LLM · eval coverage.
6. **"What is real, what is simulated"** box.
Below the fold: setup and one-command demo/deploy, data licences, consent/privacy with the half-page threat model, evaluation results (link to `eval/`), Antigravity/AI Studio/Vertex evidence as screenshots of walkthrough artifacts, cost sheet, scale story (link to `docs/scale.md`), pilot (link to `docs/pilot.md`), decisions and what did not work. Keep the sample data slice small enough that the clone is fast.

## 12. Evaluation table to ship
Forecast backtest MAPE and bias by tier and model (public series if licensed, else labelled synthetic); Planner schema-validity rate first attempt vs after revision; gate-pass-after-revision rate; guardrail unit-test count; copy validator pass rate; tool-trajectory match on ~50 gaps; Gemini-as-judge rationale score with a 15-item human-labelled agreement subset; Agent Simulation guardrail pass rate over ~200 personas; pilot: treated vs holdout with CI (show one CI crossing zero), unmeasured count, pre-registered metric; Customer Agent p50/p95 and approve → re-forecast latency; vision read accuracy on 30 staged photos; Sense and Planner throughput (300 SKUs × 10 nodes in N minutes) and the extrapolation; cost from the billing export with Gemini tokens per play. All of it committed under `eval/` as raw outputs plus a filled table in the README and on slide 9, produced at freeze (2 Oct), never typed by hand. Rename any "ablation" to "priors update sanity check".

---

## 13. Submission checklist
- [ ] Public repo, first commit after 1 Sept, no employer code/data, `DATA_LICENSES.md`, sample synthetic slice, CI green
- [ ] Live URL without login (judge mode), seeded golden plays, reset button, **min-instances=0 (scale-to-zero; see §4.5)**, weekly smoke test scheduled
- [ ] Video under 3 minutes, opens on the legal-deadline hook
- [ ] Deck in rubric order with weights; competitor slide; what-is-simulated box
- [ ] README with quick-start card, diagram, how-Gen-AI-is-used table, consent/privacy, Antigravity/AI Studio/Vertex evidence, cost sheet
- [ ] Registration approved (batched; watch the registered email) and team of 2–4 JAPAC professionals confirmed on the portal by 11 Oct
- [ ] Documentation PDF covers, explicitly and in this order: what it does; impact; theme alignment and the specific problem inside the theme; how the prototype addresses it; user guide; longevity (production path, scalability, feasibility) — all in English
- [ ] The two travelling members hold valid passports and have checked Singapore visa timelines; start the visa process the day the shortlist is announced (7 Nov) or earlier
- [ ] Deadline (18 Oct) re-verified on the portal in the final week

---

## 14. Verify before building (day 1–3)
1. Model Garden: the exact ID string for Gemini 3.8 Flash (the Google speaker named it as the recommended starting model, so it exists [Certain]; the ID string still needs confirming) and for the Live model; retirement dates through 4 Dec.
2. `AI.FORECAST` option names and TimesFM version; whether TimesFM-3 (multivariate) has landed in BigQuery [Likely imminent].
3. `ARIMA_PLUS_XREG` future-regressor table shape for `ML.FORECAST` / `ML.EXPLAIN_FORECAST`.
4. Kannada quality on the Live model and on TTS; fallback language.
5. Vision read accuracy on staged pallet photos (10 photos, two-pass if needed).
6. Region availability of BigQuery ML/TimesFM, Agent Engine Sessions and Agent Simulation in asia-south1.
7. Dunnhumby permission; fallback decision by end of week 1.
8. Looker Studio embed with owner's credentials.
9. Hack2skill portal: registration close date, submission deadline, finale demo format and duration.
10. Explainer video: reviewed from the transcript; nothing in it contradicts this guide. It confirms the 18 Oct deadline, the top-50 shortlist, batched registration approval, English-only submissions, the documentation contents including a longevity section, Gemini 3.8 Flash as the recommended model, evals as expected practice, and IP staying with the team.

---

## 15. Cut list (4-person) and never-cut
Cut in order if time runs out: voice live on stage (keep recorded) → domain-agnostic beat slide → policy-change beat (only if the Planner cannot be made to change reliably; otherwise keep) → vision two-pass refinement → Looker embed (native chart instead) → interviews beyond 4.
Never cut: the legal-deadline gap, vision intake, forecast with XREG and the approve → chart-moves beat, Play object with estimator and gate, Play Desk with trace and replay, minimal chat with stock-grounded substitution and STOP, holdout assignment and Measure with "unmeasured" enforced, the real pilot, the what-is-simulated box.

---

## 17. Verification harness: builder + reviewer loop, executable contracts, one command that says "demo-ready"

**What this can and cannot promise.** No harness makes a four-week build one-shot; what it does is make every defect visible at the commit that introduces it, fix the mechanical ones automatically within a bounded loop, and reduce your personal verification to three things: spec changes, the pilot, and the video. The rule is: **nothing is "done" because someone says so; it is done when `make verify` is green on the demo tenant.**

### 17.1 Principles
1. **The spec is executable.** Every contract in this guide exists as a file that a machine checks: `docs/schemas/play.schema.json`, tool input/output schemas, the chat envelope schema, `openapi.yaml`, BigQuery DDL plus SQL assertions, golden fixtures. Prose in the guide is not the contract; the files are.
2. **Definition of done per component = its acceptance tests** (§17.3). A component's pull request cannot merge until its tests pass in CI and the reviewer agent's checklist verdict is green.
3. **Two agents, never one.** A Builder agent implements from one spec section; a separate Reviewer agent with a different prompt, the spec, the acceptance checklist and the test output reviews the diff and either passes it or returns findings. The builder fixes; maximum three loops; then a human. The builder never marks its own work done.
4. **Deterministic gates decide; the LLM reviewer advises, except where it is the only thing that can check** (spec conformance, rationale quality, screen matches the spec). Those checklist items are marked "reviewer-verified" and require the reviewer's explicit pass.
5. **One golden path is the truth.** Capture → gap → plan → approve → chart moves → chat delivers → order → measure, on the demo tenant, from a clean snapshot, is run on every merge to main and nightly. If it is green, the demo works.
6. **Runtime invariants, not just tests.** Money math, holdout exclusion and consent are re-checked independently at runtime on every play and every offer; a violation blocks the action and alerts.

### 17.2 The loop, concretely (Antigravity or any two agent sessions)
- **Workspaces:** one Builder workspace and one Reviewer workspace in Antigravity's manager surface (or two separate agent sessions). The Reviewer never edits code; it reads the diff, runs `make verify`, and writes a verdict file.
- **Unit of work:** one spec section (e.g. §5.3 Planner tools) → one branch → one PR. The Builder receives: the spec section, the acceptance checklist for that component (§17.3), the schemas, and the command to run.
- **Builder prompt contract:** implement only what the section says; do not change schemas or other components; run the component's tests and the golden path locally; stop and report if the spec is ambiguous instead of guessing.
- **Reviewer prompt contract:** given the diff, the spec section, the checklist and the CI output: (1) confirm every checklist item with evidence (file:line, test name, screenshot); (2) look for logic errors the tests do not cover (wrong sign in margin math, holdout leakage, off-by-one on the sell-by rule, hard-coded model ID, secrets in code); (3) verdict `PASS` or `FAIL` with a numbered findings list, each with the failing item and the expected behaviour. The Reviewer is told to default to FAIL when uncertain.
- **Auto-correction:** on FAIL, the findings and the failing test output are fed verbatim back to the Builder; it patches; CI re-runs; the Reviewer re-reviews only the findings. Three loops maximum; the fourth attempt escalates to the human owner with the findings history attached.
- **Human touchpoints:** approving a spec change (a change to any file in `docs/schemas`, `openapi.yaml` or `data/bigquery/ddl` requires a human approval in CI), the weekly golden-path review, the pilot, the video. Everything else you read on the status board (`STATUS.md`, regenerated by CI: one row per component, checklist completion, last `make verify` result, open findings).
- **In CI (GitHub Actions):** `make verify` on every PR; a `spec-review` job that calls Gemini via Vertex with the Reviewer prompt, the diff and the checklist, and posts the verdict as a PR check (required for merge on items marked reviewer-verified); a nightly golden-path run against the demo tenant with an alert; a weekly live-URL smoke test through 4 Dec.

### 17.3 Acceptance tests per component (definition of done)
| Component | Deterministic tests (CI gate) | Reviewer-verified items |
|---|---|---|
| Schemas and DDL | JSON Schema validates 20 golden plays and rejects 20 mutated ones (missing citation, holdout < 0.05, negative units); DDL applies on a fresh dataset; every table has partition/cluster spec; Pydantic and TS types regenerate from the schema with no diff | Schema matches §2.4 field-for-field |
| Synthetic generator | Seeded run is byte-identical twice; row counts within spec; `online_sellby_date ≤ expiry_date` for all food rows; no pet SKUs; planted situations present (assertions by id); consent table covers every customer | Planted situations match the demo script |
| Sense: forecasts | Backtest job runs on the sample slice; MAPE per tier computed and written; every sku × cluster has a p10 ≤ p50 ≤ p90 row per horizon day; `future_regressors` has a row for every forecast date; re-forecast of one series with a play added changes p50 in the play window and nowhere before it | Model choice per tier matches §5.2; no `holiday_region` on the TimesFM call |
| Sense: gaps | Gap ₹ recomputed by an independent SQL implementation equals the pipeline's within 1 rupee; `online_sellby_breach` uses the versioned `sellby_rule`; a batch past its sell-by never yields an online play | Evidence struct is complete and citable |
| Segments and substitutes | KMEANS k = 6 with named segments; every customer has a segment; substitutes are same-category and top-5; at chat time substitutes with zero stock are filtered | Segment names are human-readable |
| Estimator and gate (`agents/gate`) | 100% branch coverage on the eight rules; property tests: margin after discount never below floor when gate passes; holdout fraction respected within 1% on 10,000 hashed customers; `cite_or_drop` rejects an uncited number; counterfactual arithmetic matches a spreadsheet fixture | Prior derivation documented and weak by construction |
| Planner Agent | `adk eval` on 50 gaps: schema validity ≥ 95% after revision, gate-pass-after-revision ≥ 90%, trajectory match on the required tool order; the tea gap changes mechanic when the policy fixture changes; loop terminates within 3 iterations on 50/50 | Rationale quality on a 15-item human-labelled subset; no number in a rationale that is not in `citations` |
| Approve and assignment | Idempotent (double approve = one assignment set); arm assignment reproducible from seed; holdout customer never appears in `offers/`; `future_regressors` gains the play; single-series re-forecast returns in < 15 s on the demo tenant | UI state after approve matches §5.6 |
| Customer Agent | Scripted conversations (20) pass: offer delivered with best-before line; out-of-stock → substitution from live stock; holdout customer asking "any offers?" gets none; STOP writes `withdrawn_at` and stops delivery; coupon stacking refused; p95 < 6 s on 50 runs; Agent Simulation guardrail pass rate ≥ 95% over ~200 personas | Tone and language per persona; wire envelope matches the schema on every message |
| Stylist Agent | Scripted conversations (14) pass: colour theory is plain Python, no LLM scores a pairing; every ask recorded deterministically to `style_requests`; unknown colour degrades to neutrals; a photo read validates its schema and a low-confidence read is said out loud; a selfie is never saved without confirmation and never reaches `style_requests`/`style_trends`; stylist and grocery sessions never collide for the same `customer_id:web` | Tone and language per persona; pairing reasons and skin-tone notes read as styling advice |
| Vision intake | 30 staged photos: date read accuracy ≥ 90% at confidence ≥ 0.7; rows under 0.7 always produce a confirmation question; output validates against the intake schema | Two-pass fallback engaged when single-pass fails |
| Voice (if kept) | Tool calls fire for the three intents on 20 recorded Kannada and English clips; fallback language switch works | Spoken play summary matches the play card |
| Measure | Fixture with known outcomes reproduces lift and CI to 3 decimals; play below `min_treated_n` is `unmeasured`; priors update alpha/beta by exact counts; dashboard never shows an unmeasured lift | Outcomes screen number equals the Looker number equals the README number |
| Web (Play Desk, phone, chat, judge mode) | Playwright: "Run the 60-second beat" completes in < 30 s with the chart change visible; "Chat as Meena" first reply < 6 s; reset restores the snapshot; per-visitor sandbox isolation (two sessions do not see each other's approvals); no console errors; mobile viewport passes; LIVE/REPLAY badges present on every panel; first paint < 4 s from a cold hit | Screens match §5.6; no login wall |
| Event log and replay | Replay of a golden run renders the same panel states as the live run (snapshot diff); every ADK event persisted with `ts_offset_ms` | Trace is readable to a judge |
| Infra and deploy | `make deploy` from a clean project succeeds; `/health` reports all four dependencies; IAM matrix applied (each service account least-privilege, checked by a script); secrets absent from the repo (secret scan); model IDs only in config; budget alerts exist | Region and pinning match §4.4 |
| Docs and submission | README lint (quick-start card first, links resolve, screenshots exist); video file length ≤ 2:45; links public (fetched in an incognito-like check); deck PDF opens; documentation PDF exists; `DATA_LICENSES.md` present; no third-party raw data in the tree | Slide 2 and the closing card carry the same number as Outcomes |

### 17.4 `make verify` (the single command)
Runs, in order, and stops at the first red: secret scan → schema/DDL tests → generator determinism → gate/estimator unit and property tests → SQL assertions on the demo dataset → `adk eval` → scripted conversations + Agent Simulation → vision accuracy → Playwright judge-mode suite → golden path end-to-end on a fresh snapshot → docs/submission lint. Output: `STATUS.md` and a one-line verdict. Green = demo-ready; the video is shot only from a green build; the finale is rehearsed only on a green build.

### 17.5 Runtime invariants (independent of the tests)
On every play write: an independent function recomputes expected margin, discount cost and waste avoided and blocks the write on mismatch. On every offer delivery and `apply_offer`: arm = treated, consent present, frequency cap respected, or the action is refused and logged. On every re-forecast: p50 outside the play window unchanged versus the previous run, else alert. On every Measure run: any lift shown without a holdout fails the job. Alerts go to the team channel; the judge-mode footer's health strip turns amber.

### 17.6 Where the harness sits in the plan
Week 1, before features: schemas, DDL, generator determinism, CI skeleton with `make verify` running the empty suites, the Builder/Reviewer prompts and the `spec-review` job, `STATUS.md` generation. Owner D builds the harness; owner B writes the Reviewer prompt and the acceptance checklists from §17.3 into `harness/checklists/*.md`. Every component afterwards lands through the loop. Add to the repo layout: `tests/` (unit, property, sql, playwright), `harness/` (builder and reviewer prompts, checklists, `spec-review` action, status generator), `fixtures/` (golden plays, conversations, photos, outcomes).

---

## 18. Cost-minimal multi-agent framework: any business size, cost a fraction of the rupees at stake

**Design goal, stated so it can be tested:** the total cost of running Taal for a tenant must stay under **2% of the rupees at stake** it acts on, and a single small shop must run for **under ₹500 a month**, with no fixed infrastructure cost when idle. "Minimal" is enforced by an agent and a budget, not assumed. All prices below are list prices found in September 2026 search results and every monthly figure is an estimate [Likely on prices, Guessing on the monthly totals]; the build measures the real numbers from the billing export and prints them on the Play card, the dashboard and slide 10.

### 18.1 Why the cost is naturally low, and where it is not
The expensive things in agent systems are idle infrastructure and conversations. Taal's nightly work is batch (BigQuery compute, a bounded number of Planner runs); its serving is scale-to-zero; the only per-customer LLM cost is a chat turn, and a chat turn happens only when a customer replies. Proactive delivery of a play is a stored message, not an LLM call. So the cost driver is **conversations per play**, and the second is **Planner runs per night**. Both are governable.

### 18.2 The agent roster with a Cost Governor in it
| Agent | Job | Model tier | Why that tier |
|---|---|---|---|
| **Triage / Cost Governor** (new; deterministic with one small LLM call) | Ranks gaps by ₹ at stake; decides which gaps get a Planner run tonight under the tenant's budget; picks the model tier per task by expected value; chooses batch vs live; degrades gracefully (fewer copy variants for tiny audiences, reuse of a cached rationale pattern for repeat gaps); writes `cost_per_play` and `budget_remaining` to the trace | Rules + Flash-Lite for the one classification it needs | Its own cost must be near zero |
| Capture (vision, voice) | Reads pallet photos; handles the manager's spoken question | Flash for vision (one call per photo); Live model only while a session is open; **Gemma 4 on-device via Firebase AI Logic hybrid inference for a free first-pass label/date read on the phone, with cloud fallback** [Likely available; verify] | Photos are few; voice is per session |
| Planner | Designs the play, revises on guardrail failure | Flash, `thinking_level` low for routing turns and medium only for the final proposal; Pro never by default; **Batch API for the nightly fan-out (50% off)**; explicit context caching of the policy text and product context across the night's runs (cached input ~90% cheaper) | 60–90% of Planner spend saved versus naive live Pro calls |
| Copy | Vernacular variants per segment × language | Flash-Lite via `AI.GENERATE_TABLE`, only for approved plays, only for segments above a minimum audience size; templated copy for micro-audiences | Cheapest tier; row cap by policy |
| Customer | Delivers and answers | Flash with streaming, `thinking_level` low; first turn served from the stored offer without an LLM call; cached tenant context; conversation capped at N turns per session | Conversations are the main variable cost; each lever cuts it |
| Measure | Treated vs holdout, priors | No LLM; BigQuery only | Free within the 1 TiB/month tier for small tenants [Certain on the tier] |
| Reviewer (build-time only, §17) | Reviews diffs | Flash | Development cost, not runtime |

### 18.3 Levers, in order of effect
1. **Gate compute by rupees at stake.** No Planner run for a gap whose ₹ at stake is below a tenant threshold (default ₹500); such gaps get a templated suggestion. This alone bounds nightly spend to the gaps that matter.
2. **Batch, don't stream, at night.** Planner fan-out and copy generation run through the Batch API (half price, up to 24 h; the nightly window tolerates it) [Certain on the 50% discount].
3. **Cache what repeats.** Policy text, product context and the segment catalogue are cached inputs; per-turn tenant context for the Customer Agent is cached at conversation start.
4. **Serve from Firestore, compute in BigQuery.** No LLM reads BigQuery at chat time; stock, offers and substitutes are precomputed nightly. BigQuery bytes scanned stay small with partitioning and clustering.
5. **Scale to zero.** Cloud Run `min-instances=0` in production -- **this is the actual deployed decision for the whole judging window (§4.5), not just demo days**; measured cold start is materially over the ~3s estimate here (see eval/evaluation.md). Cloud Run Jobs for nightly work (1-minute minimum billing). No Vertex AI Vector Search endpoints, no AlloyDB, no Looker Core [Certain on those cost traps].
6. **Tier the models by task, never by habit.** Flash-Lite for classification and copy; Flash for reasoning and vision; Live only during a voice session; Pro only behind an explicit "deep look" the merchant pays for.
7. **Cap conversations.** Turns per session, sessions per customer per play, and a per-play conversation budget the Cost Governor sets from the ₹ at stake.
8. **Multi-tenant by default.** `tenant_id` on every table; one deployment serves many shops; fixed costs (nightly job, monitoring) are shared.
9. **Edge for free where it fits.** Gemma 4 on-device for the phone's first-pass read and for an offline stock lookup [Likely]; the cloud is called only when confidence is low.
10. **Measure cost as a first-class metric.** `cost_per_play`, `cost_per_1000_customers`, `cost_as_pct_of_rupees_at_stake` computed from the billing export and Gemini token counts; shown on the Play card, the Outcomes screen and the dashboard; the Cost Governor alerts when a tenant exceeds its budget.

### 18.4 Unit-cost model (estimates from list prices; measure and replace)
Assumptions: Flash ≈ $0.75 per million input tokens and $3.75 per million output through 2026, cached input ≈ 90% cheaper, Batch API 50% off; Flash-Lite ≈ $0.30 / $2.50 [Likely on all]. ₹ at ~83 per $.
- **One Planner run:** ~3 loops × (6k input + 1.5k output) ≈ 18k in, 4.5k out → ≈ $0.03 live; ≈ $0.015 in batch; ≈ $0.01 with the policy and product context cached. **≈ ₹1–2.5 per play.**
- **Copy for one play:** 6 segments × 2 languages × (500 in, 200 out) on Flash-Lite → ≈ $0.005. **≈ ₹0.4.**
- **One pallet photo:** ≈ 1.3k in, 0.5k out on Flash → ≈ $0.003. **≈ ₹0.25.**
- **One customer conversation:** ~5 turns × (3k in mostly cached, 300 out) → ≈ $0.01–0.017. **≈ ₹1–1.5 per conversation**; delivery of the offer itself costs nothing.
- **Per play, all in:** Planner + copy + (conversations × reply rate). For a play to 1,000 customers with a 10% reply rate: ≈ ₹2 + ₹0.4 + 100 × ₹1.3 ≈ **₹130–150**, against a typical ₹9,200 at stake: **≈ 1.5%**. The Cost Governor enforces the 2% ceiling by capping conversations or skipping copy variants for the smallest segments.

### 18.5 Deployment profiles (what "any business size" means in practice)
| Profile | Who | Footprint | Estimated monthly cost |
|---|---|---|---|
| **Micro** | one shop, one node, ≤ 500 SKUs, ≤ 1,000 customers, ~2 plays a day | Shared multi-tenant deployment; Firestore only for serving; BigQuery within the free tier; phone view with on-device first pass; no Looker (native chart) | Gemini ≈ ₹150–300; everything else inside free tiers → **≈ ₹200–500** |
| **Mid** (the demo persona) | 300 SKUs, 10 nodes, 6 outlets, ~4,000 customers, ~30 plays a night, ~500 conversations a month | Same deployment; BigQuery a few GB; Cloud Run scale-to-zero; nightly job; Looker Studio (free) | Planner ≈ ₹900–2,000; conversations ≈ ₹700; BigQuery ≈ ₹400–1,600; Cloud Run/Firestore ≈ ₹0–800 → **≈ ₹2,500–5,000** |
| **Large** | 20,000 SKUs, 500 nodes, 1M customers, ~2,000 gaps a night after triage, ~20,000 conversations a month | Dedicated project; Cloud Tasks fan-out; batch Planner; partitioned BigQuery; still scale-to-zero serving | Planner ≈ ₹60,000–150,000 (batch + caching, triaged); conversations ≈ ₹26,000; BigQuery ≈ ₹8,000–25,000; Cloud Run ≈ ₹4,000–8,000 → **≈ ₹1–2 lakh**, against rupees at stake in the crores |

All three profiles run the same code with a tenant config; the difference is triage thresholds, budget caps and whether Looker Studio is attached. The Micro profile is the answer to "can a kirana use it": yes, because idle cost is zero and the Governor never spends more than the gap is worth. [Guessing on every rupee figure; the build replaces them with measured numbers]

### 18.6 What this adds to the entry
One slide (§11 slide 10 already exists; add the profile table and the 2% rule), one line on the Play card ("this play cost ₹1.8 to plan; conversations budgeted ₹40"), the Cost Governor visible as a named agent in the trace, and `docs/scale.md` carrying the measured unit costs. It answers the scalability sub-criterion with numbers and it answers a retail CEO's "what does this cost me" before they ask.

---

## 19. Y Combinator Requests for Startups: what maps onto Taal (Spring, Summer and Fall 2026 lists, read via secondary summaries; ycombinator.com was unreachable from this session)

Most of the 2026 lists are irrelevant here (defence, space manufacturing, inference chips, agriculture robots, biology). Four items map, and they are worth using because judges' "longevity, scalability, feasibility" section is a business-model question and YC's language is the current vocabulary for it. [Likely on the RFS wording; from summaries, not the YC page]

| RFS item | What YC asks for | What it adds to Taal | Cost |
|---|---|---|---|
| **AI guidance for physical work** (Spring 2026): a multimodal copilot that sees what the worker sees and guides the task step by step, with evidence photos and audit events | After Approve, the phone view turns the play into **guided physical steps for Priya** (for `transfer_plus_nudge`: "move 120 units of batch B-7 to Koramangala outlet, print this shelf tag"; for `outlet_markdown`: the tag and the shelf), asks for an **evidence photo** when done, and writes an `execution_events` row. This closes the loop in the physical world and is the strongest "physical + digital" proof in the entry. | ~10 h (C + B); add to §5.6 and §17.3; never-cut if week 2 is on plan |
| **Software for Agents** (Summer 2026): "the next trillion users are agents"; build APIs, MCPs and machine-readable surfaces | Expose the Play Desk as an **MCP server** (`list_gaps`, `get_play`, `approve_play`, `get_outcomes`) so a retailer's own CRM or planning agent can consume plays without the UI; the play schema is already machine-readable. One slide line: "Taal's users can be agents." Pairs with the UCP roadmap note. | ~8 h (B); week 3 only if the gate passed on time; otherwise a roadmap line |
| **Company Brain / AI Operating System for Companies** (Summer 2026): a living, executable map of how a company decides (how refunds are processed, how pricing exceptions are decided) | Frame the **policy editor + measured priors + play outcomes** as the merchant's executable decision memory: how this retailer decides markdowns, transfers and exceptions, kept current by measurement. This is the longevity story: the asset that accumulates is the tenant's decision record, not the model. | 0 h; documentation and deck framing (§11 slide 10, documentation PDF longevity section) |
| **SaaS Challengers** (Summer 2026): AI-native replacements for the categories incumbents charge most for, supply-chain management named explicitly; and **AI-native service companies** (Summer 2026): do the work at software margins | Position Taal in the longevity section as an AI-native challenger to mid-market planning suites, with the §18 cost profiles as the proof that the unit economics work at every size, and the Micro tier as a managed service ("demand shaping as a service" for a single shop). | 0 h; framing |

Not adopted: Dynamic Software Interfaces (users rebuilding the UI; out of scope), Multiplayer AI (Fall 2026; the approval loop already has humans and agents collaborating, say so in one line, build nothing).

Scope note: the two build items add ~18 h to a plan that already has thin slack (§8). The physical-guidance beat is worth it; the MCP surface is conditional on the week-2 gate.

---

## 16. Alternatives considered (from the contrarian review; parked, on the roadmap slide)
- **Dwaar** (merchant-side agentic commerce): an ADK merchant agent exposing catalogue, stock, substitutions and checkout over UCP with AP2 mandates, bridged toward ONDC, negotiating with shopper agents. Projected ≈ 74/77; highest innovation ceiling against Google's own protocol push; weakest "who pays now"; protocol and ONDC-sandbox risk. [Guessing on scores]
- **Seedha** (Gemini Live co-host for live-stream selling on Shopee/TikTok/Meesho Live): projected ≈ 72 at shortlist, 78 if the live beat works, ~68 if not; no Google product touches it; highest stage risk; poor fit to an ops/data team. [Guessing on scores]
- Taal v3 (this guide): projected ≈ 74–77 by the same reviewer, lowest failure surface, best fit to your edge. The three sit in the same band; the choice is variance and fit, and it is yours.
