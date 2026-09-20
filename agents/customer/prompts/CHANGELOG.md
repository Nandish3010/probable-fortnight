# Customer prompt changelog

- v2 (2026-09-20): stock tools return an availability band instead of the on-hand count, and the prompt forbids stating a quantity. The first live Vertex run answered "Cola Zero 1L -- Qty: 127"; the stub had been worded around the rule since 32fda53 but the model was still handed the number.
- v1 (2026-09-12): initial. First-turn offer delivery from the tool only; stock-grounded substitution; STOP handling; JSON envelope output.
- v2 (2026-09-12): seventh tool `list_products` for browse and category questions; greeting only on whole words; JSON envelope unchanged.
- v3 (2026-09-12): reply in the customer's message language, not only their stored preference; "discount" recognised as an offer synonym with last-shown-product context; order confirmation names every line including a bundle partner added silently.
