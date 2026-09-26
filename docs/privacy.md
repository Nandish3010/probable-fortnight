# Privacy

Half-page threat model for Taal (DECISIONS §2.6, §3.2, §5.6). Framed under India's DPDP Rules
2025 (Digital Personal Data Protection); [likely on exact rule citations -- verify against the
final published rules before any real-tenant deployment].

## What leaves the tenant

Nothing by default. BigQuery (system of record) and Firestore (serving cache) live inside the
tenant's own Google Cloud project; the only outbound calls are to Vertex AI (Gemini, embeddings)
for model inference, which Google's Vertex AI terms treat as not used to train foundation models
by default for enterprise customers [likely -- verify the current Vertex AI data-use terms at
deploy time, they have changed before]. No customer data is sent to any third party beyond
Google Cloud/Vertex AI. The Looker Studio embed reads BigQuery through the owner's own
credentials with "anyone with the link" sharing -- this makes the **dashboard link** shareable,
not the underlying customer PII, since the dashboard's cards are aggregates (DECISIONS §5.8).

## Where photos live and for how long

A pallet photo is uploaded to Cloud Storage and referenced by `capture_ref` on the
`inventory_batches` row it produced. Photos contain shelf/product images, not customer data.
Retention: photos are kept for as long as their `inventory_batches` row is useful for audit (the
batch's shelf life plus a short buffer), then deleted by a lifecycle rule on the bucket; the
`crop_ref` used mid-pipeline for the two-pass read is deleted once the confirmation question is
answered. No photo is used for anything other than stock intake -- it is not linked to a customer
identity at any point. (The one exception, a selfie for the stylist's skin-tone read, is covered
separately below -- unlike a pallet photo, it is never stored at all, not even briefly.)

## Style profile and selfies

The Stylist Agent's skin-tone profile is opt-in twice over: the customer chooses to share it (by
button or by selfie), and nothing is saved until they confirm the coarse read back. A garment photo
follows the pallet-photo pattern above (read once, not retained beyond the read); a **selfie is
stricter still: the image bytes are never written to disk, a bucket, or any table, at any point**
-- `agents/stylist/vision.py` takes the upload in memory, reads two coarse attributes (undertone:
warm/cool/neutral; depth: light/medium/deep) and discards the bytes when the call returns. What
persists is `customer_style_profile`: those two enums, a `source` (declared or selfie), and a
`consent(purpose="style_profile")` row alongside the existing `marketing` purpose -- never a photo,
never a finer-grained reading, never anything read as ethnicity or any protected characteristic.
"Forget my skin tone" withdraws that consent row and deletes the profile synchronously, the same
immediacy STOP gives marketing consent. The profile is read only inside `suggest_pairings` to bias
a pairing's score by at most ±0.10 for items worn near the face; it is never joined into
`style_requests` or `style_trends` (neither table has a skin-tone column), never read by Sense or
the Planner, and never shown to anyone but the customer it belongs to.

## What the Customer Agent can and cannot see

**Can see** (via its six tools, all reading from precomputed/serving stores, never live BigQuery):
the requesting customer's own `home_node_id`, `language`, `pending_offers`, and arm-per-play
(`get_customer_context`); live stock and dates for a SKU at a node (`get_stock`); precomputed
substitute candidates filtered by current stock (`find_substitutes`); its own conversation
history in the current session.

**Cannot see**: any other customer's data, ever -- every tool call is scoped to the session's own
`customer_id`; any BigQuery table directly (all chat-time reads are Firestore or Sessions, per
DECISIONS §18.2 "no LLM reads BigQuery at chat time"); a holdout customer's arm status framed as
anything other than "no pending offer" (the agent does not say "you are in the holdout group" --
it simply has nothing pending to deliver, and `apply_offer` refuses on arm=holdout without
revealing why); consent-withdrawn customers' pending offers (filtered before they ever reach the
agent's context).

## The STOP flow

A customer sending "STOP" (or an equivalent phrase the Customer Agent recognises) calls
`record_stop(customer_id)`, which sets `consent.withdrawn_at` for that customer's marketing-purpose
consent row. From that point: the gate's `consent_required` guardrail excludes the customer from
every future audience; the nightly Firestore mirror stops writing `offers/{customer_id}` for them;
and a direct "any offers?" question gets no offer, the same as a holdout customer, without
distinguishing the two reasons in the reply. STOP is honoured immediately, not on the next nightly
run -- `record_stop` writes `withdrawn_at` synchronously.

## DPDP framing

Consent is a first-class table (`taal.consent`: `customer_id, channel, purpose, source, ts,
withdrawn_at`), read by the gate before any audience is built and shown shrinking after the
consent filter on the Play Desk (DECISIONS §2.6). This is deliberately "consent-native by
design": the audience for a marketing play is *never* "everyone at this node with this SKU
history" -- it is always "everyone at this node with this SKU history AND an active consent row
for this channel and purpose." Withdrawal is a first-class, immediate action, not a settings-page
afterthought. This is the DPDP-aligned shape (purpose limitation, consent as a revocable record,
no dark-pattern re-consent), stated here as a design commitment, not a legal opinion -- a real
tenant deployment needs its own DPDP compliance review before launch.

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
as the pilot conversation they were given for is over, if that is sooner. [Retention period is
the team's decision to confirm before the form is shared -- this document states 12 months and
the consent text on the form says the same; change both together.]

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
