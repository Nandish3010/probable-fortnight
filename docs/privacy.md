# Privacy

Half-page threat model for Taal (DECISIONS §2.6, §3.2, §5.6). Framed under India's Digital
Personal Data Protection Act, 2023 (DPDP Act) and the DPDP Rules, 2025, notified in November 2025;
the Rules phase in over 18 months, with the main obligations on data fiduciaries applying from
May 2027.

## What leaves the tenant

Nothing by default. BigQuery (system of record), the per-visitor local store that serves chat-time
reads, and Firestore (practitioner feedback in the deployed service, `TAAL_FEEDBACK_STORE=firestore`
in `infra/deploy.sh`; an optional stock/customer-profile serving cache also exists behind
`TAAL_SERVING_CACHE=firestore`, which `infra/deploy.sh` sets only when a maintainer flips
`ENABLE_SERVING_CACHE` from its hard-coded default of 0 (`infra/deploy.sh:22`), so the cache is
off in the deployed service today) all live inside the tenant's own Google Cloud project; the only outbound calls are to Vertex AI (Gemini, embeddings)
for model inference. Google's Vertex AI documentation says "Google won't use your data to train or
fine-tune any AI/ML models without your prior permission or instruction"
([data governance](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/data-governance)).
No customer data is sent to any third party beyond
Google Cloud/Vertex AI. A Looker Studio report over `play_outcomes`, reading BigQuery through the
owner's own credentials with "anyone with the link" sharing, is designed but not wired into this
repo (DECISIONS §5.8; see `docs/architecture.md` for what the Outcomes page actually shows). If
built as designed, this would make the **dashboard link** shareable, not the underlying customer
PII, since the dashboard's cards are aggregates.

## Where photos live and for how long

A pallet photo is uploaded to Cloud Storage and referenced by `capture_ref` on the
`inventory_batches` row it produced. Photos contain shelf/product images, not customer data.
Retention: photos are kept for as long as their `inventory_batches` row is useful for audit (the
batch's shelf life plus a short buffer), then deleted by a lifecycle rule on the bucket; the
`crop_ref` used mid-pipeline for the two-pass read is deleted once the confirmation question is
answered. No photo is used for anything other than stock intake -- it is not linked to a customer
identity at any point.

## What the Customer Agent can and cannot see

**Can see** (via its six tools, all reading from precomputed/serving stores, never live BigQuery):
the requesting customer's own `home_node_id`, `language`, `pending_offers`, and arm-per-play
(`get_customer_context`); live stock and dates for a SKU at a node (`get_stock`); precomputed
substitute candidates filtered by current stock (`find_substitutes`); its own conversation
history in the current session.

**Cannot see**: any other customer's data, ever -- every tool call is scoped to the session's own
`customer_id`; any BigQuery table directly (chat-time reads go through the per-visitor local store
-- `LocalStore`/`OverlayStore` over the frozen snapshot -- or ADK session state, never live
BigQuery, per DECISIONS §18.2 "no LLM reads BigQuery at chat time"; an optional Firestore serving
cache also exists behind `TAAL_SERVING_CACHE`, which `infra/deploy.sh` sets only when a maintainer
flips `ENABLE_SERVING_CACHE` from its hard-coded default of 0 (`infra/deploy.sh:22`), so it is off
in the deployed service today); a holdout customer's arm status framed as
anything other than "no pending offer" (the agent does not say "you are in the holdout group" --
it simply has nothing pending to deliver, and `apply_offer` refuses on arm=holdout without
revealing why); consent-withdrawn customers' pending offers (filtered before they ever reach the
agent's context).

## The STOP flow

A customer sending "STOP" (or an equivalent phrase the Customer Agent recognises) calls
`record_stop(customer_id)`, which sets `consent.withdrawn_at` for that customer's marketing-purpose
consent row, always in the visitor's own store: consent and offers are never served from the
Firestore serving cache (`TAAL_SERVING_CACHE=firestore`, off in the deployed service today --
`infra/deploy.sh` sets it only when a maintainer flips `ENABLE_SERVING_CACHE` from its hard-coded
default of 0, `infra/deploy.sh:22` -- and even then the cache mirrors stock and customer-profile
docs only), so turning that flag on cannot delay a STOP. From that point: the gate's
`consent_required` guardrail excludes the customer from every future audience; and a direct "any
offers?" question gets no offer, the same as a holdout customer, without distinguishing the two
reasons in the reply. STOP is honoured immediately, not on the next nightly run --
`record_stop` writes `withdrawn_at` synchronously.

## DPDP framing

Consent is a first-class table (`taal.consent`: `customer_id, channel, purpose, source, ts,
withdrawn_at`), read by the gate before any audience is built and shown shrinking after the
consent filter on the Play Desk (DECISIONS §2.6). This is deliberately "consent-native by
design": the audience for a marketing play is *never* "everyone at this node with this SKU
history" -- it is always "everyone at this node with this SKU history AND an active consent row
for this channel and purpose." Withdrawal is a first-class, immediate action, not a settings-page
afterthought. Mapped to the Act:

- **Consent tied to a purpose** (DPDP Act s.6(1): consent must be free, specific, informed,
  unconditional and unambiguous, for a specified purpose, and limited to the data necessary for
  it): the `purpose` column on `consent`, and the gate's `consent_required` guardrail.
- **Withdrawal as easy as giving consent** (s.6(4)): "STOP" in the same chat the offer arrived in.
- **Processing stops on withdrawal** (s.6(6): the fiduciary must cease processing within a
  reasonable time): `record_stop` writes `withdrawn_at` synchronously and the gate excludes the
  customer from every later audience.
- **Erasure** (s.8(7): erase personal data when consent is withdrawn or the purpose is no longer
  served, unless a law requires retention): applied today to the practitioner feedback dataset
  (see "Deletion on request" below); the demo tenant's customers are synthetic.

A tenant deployment needs its own DPDP compliance review before launch.

## Practitioner feedback

A separate, real dataset: answers from retail practitioners (store managers, planners,
quick-commerce operators, owners) to the questionnaire at `/feedback`. It is never seeded,
generated or simulated, and it is not part of the synthetic demo tenant. The questions are in
`config/feedback_form.json`; the stored shape is `docs/schemas/feedback_response.schema.json`.

**What is collected.** Answers to the questions (role, business type and size, how near-expiry
stock is handled today, opinions of Taal), optional free text, whether the respondent may be
quoted, and a consent tick. Server-assigned: a random `response_id`, `submitted_at`, the
`form_version`, and `mode` (`self`, or `interview` when a team member filled it in during a
call). No IP address, device identifier, cookie or visitor id is stored with a response. The
rate limiter keeps a per-device/IP counter in memory for an hour; it is never written anywhere.

**Contact details are optional**, and the form only asks for them (name, and email or phone)
from someone who answered Yes or Maybe to a one-week pilot. They are stored in a separate
collection (`feedback_contacts`) keyed by the same `response_id`, used only to arrange a pilot,
and never read by the summary command or the results page, so no report or export contains them.

**Why.** To understand how retailers handle near-expiry stock today and to support, with real
evidence, the impact claims in the project submission. Quotes are used only where the respondent
answered Yes to being quoted, verbatim, attributed only by role and business type.

**Where it is stored.** In production, Firestore in the project's own Google Cloud project
(`feedback_responses` and `feedback_contacts`), selected by `TAAL_FEEDBACK_STORE=firestore`.
Never on the Cloud Run container's disk, and never in the demo tenant or a visitor sandbox, so
"Reset demo data" cannot touch it. Aggregates are visible only through `/feedback/results`, behind
an admin token held in Secret Manager.

**How long.** Up to 12 months from submission, then deleted; contact details are deleted as soon
as the pilot conversation they were given for is over, if that is sooner. The consent text on the
form (`config/feedback_form.json`) states the same 12 months; change both together.

**Deletion on request.** After submitting, the respondent is shown their `response_id` as a
reference. Anyone who quotes it (by email to the team) has the response and any contact details
deleted with:

    curl -X DELETE -H "Authorization: Bearer $TAAL_FEEDBACK_ADMIN_TOKEN" \
      https://<taal-agents URL>/feedback/<response_id>

The team then re-runs `python -m harness.feedback_summary` so the next summary no longer counts
it. A summary file already committed to git keeps its aggregate counts in history; it never
contains a `response_id` or contact detail, and a quote from a respondent who later asks for
deletion is removed from the next summary. A respondent who has lost the reference can ask by
role, business and approximate date, and the team matches it by hand.
