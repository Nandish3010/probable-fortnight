---
component: vision_intake
title: Vision intake
owner: B
spec_sections: ["5.1"]
tests: ["tests/agents/test_vision.py"]
---
# Vision intake (`agents/capture`)

## Deterministic (CI gate)
- [x] 30 staged photos under `fixtures/photos/`: date read accuracy >= 90% at confidence >= 0.7 (vertex mode; stub replays the recorded reads) -- 30/30 (100%), Gemini-generated synthetic, self-tested against the live pipeline; see `eval/raw/vision_synthetic_2026-09-21.json` and `eval/evaluation.md`
- [x] Rows under 0.7 always produce a `confirmation_question`
- [x] Output validates against `docs/schemas/vision_intake.schema.json`
- [x] Confirmed rows are written to `inventory_batches` with `source=photo` and a derived `online_sellby_date`
- [x] `model_id` in the result equals the id from `config/models.toml`

## Reviewer-verified
- [x] Two-pass fallback engaged when the single-pass read is unreliable
