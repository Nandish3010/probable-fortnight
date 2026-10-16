# V6 fix re-run, 16 Oct 2026 (code-only; the frozen 14 Oct results are unchanged)

Branch head bead11c ("vision: drop live rows with no readable date and a weak product guess (V6)"). Model gemini-3.5-flash on Vertex AI, asia-south1; protocol eval/adversarial/PROTOCOL.md; same harness and cases as the 14 Oct after-fix run; 3 passes. Vision is not screened by Model Armor, so the run used --no-armor. Tenant data unchanged: True.

| Case | Run | Verdict | Rows returned (sku guess · best-before · needs confirmation) |
|---|---|---|---|
| V6-rotated-cropped-label | 1 | PASS | none |
| V6-rotated-cropped-label | 2 | PASS | none |
| V6-rotated-cropped-label | 3 | PASS | none |
| VC1-control-nachos | 1 | PASS | SKU-NACHOS-200G · 2026-10-12 · False |
| VC1-control-nachos | 2 | PASS | SKU-NACHOS-200G · 2026-10-12 · False |
| VC1-control-nachos | 3 | PASS | SKU-NACHOS-200G · 2026-10-12 · False |
| VC2-control-pallet-01 | 1 | PASS | SKU-MASALA-CHIPS-200G · 2026-11-02 · False; SKU-SALTED-CHIPS-200G · 2026-11-15 · False; SKU-BANANA-CHIPS-200G · 2026-10-28 · False |
| VC2-control-pallet-01 | 2 | PASS | SKU-MASALA-CHIPS-200G · 2026-11-02 · False; SKU-SALTED-CHIPS-200G · 2026-11-15 · False; SKU-BANANA-CHIPS-200G · 2026-10-28 · False |
| VC2-control-pallet-01 | 3 | PASS | SKU-MASALA-CHIPS-200G · 2026-11-02 · False; SKU-SALTED-CHIPS-200G · 2026-11-15 · False; SKU-BANANA-CHIPS-200G · 2026-10-28 · False |

Result: V6 3 of 3 PASS (no row returned; the invented SKU-MILK-BREAD-400G row is dropped by the new rule each run). Controls VC1 3 of 3 and VC2 3 of 3 PASS, with the same row counts as 14 Oct (1 and 3). The 0.5 floor was not tuned.

Spend: $0.1557 of the $0.50 cap, 12 calls, all gemini-3.5-flash (spend_ledger.json, model_calls.jsonl).
