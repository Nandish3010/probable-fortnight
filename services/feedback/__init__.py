"""Practitioner feedback: the one dataset in this repo that is entirely real (never seeded,
generated or simulated). Kept apart from the demo tenant on purpose -- its own schema
(docs/schemas/feedback_response.schema.json), its own store (never LocalStore/OverlayStore, so
"Reset demo data" cannot touch it), and its own switch, TAAL_FEEDBACK_STORE."""
