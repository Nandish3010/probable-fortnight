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
identity at any point.

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
