# Firestore mirror

Firestore is a serving cache, never the system of record (DECISIONS §3.3, §4.1). The Cloud Run
Job `taal-sense` writes it as the last step of the nightly run, after `01_regressors.sql` through
`08_copy.sql` have finished and after Measure has updated `play_outcomes` (DECISIONS §4.2). The
mirror step is plain Python using `google-cloud-firestore`, reading the BigQuery tables it mirrors
and overwriting each document; it never reads Firestore back into BigQuery.

## Collections and document shapes

### `stock/{node_id}/{sku}`
One document per (node, sku) actually stocked. Read by the Customer Agent's `get_stock` tool and
the phone view's gap card.

```
{
  "qty_on_hand": int,
  "nearest_online_sellby": "YYYY-MM-DD" | null,
  "nearest_expiry": "YYYY-MM-DD" | null,
  "updated_at": "<RFC3339>"
}
```
Source: `taal.inventory_batches` grouped by (node_id, sku); `qty_on_hand` = SUM over batches;
`nearest_online_sellby` / `nearest_expiry` = MIN over batches with qty_on_hand > 0.

### `customers/{customer_id}`
Read by the Customer Agent's `get_customer_context` tool.

```
{
  "language": "en" | "kn",
  "home_node_id": string,
  "arms": { "<play_id>": "treated" | "holdout" },
  "pending_offers": ["<play_id>", ...]
}
```
Source: `taal.customers` joined to `taal.play_assignments` (arms) and `offers/{customer_id}`
(pending_offers, see below -- this field is denormalised onto the customer document for a single
read on session start).

### `offers/{customer_id}`
One document per customer with at least one pending proactive delivery. Written synchronously by
Approve (DECISIONS §5.4) for every treated customer, then mirrored here again on the nightly pass
for any offer a session has not yet consumed.

```
{
  "pending": [
    {
      "play_id": string,
      "sku": string,
      "copy_text": { "en": string, "kn": string },
      "disclosure_included": bool,
      "best_before": "YYYY-MM-DD" | null,
      "created_at": "<RFC3339>"
    }
  ]
}
```
Source: `taal.plays.play_json.copy.variants` for approved plays, filtered to the customer's
segment and language, joined against `taal.play_assignments` for arm = 'treated' only -- a
holdout customer's document is never written here (DECISIONS §5.4, §17.5).

### `plays/{play_id}`
Status snapshot for the Play Desk's live reads.

```
{
  "status": string,
  "objective": string,
  "mechanic": string,
  "sku": string,
  "target_node_ids": [string],
  "expected_outcome": { "units": int, "margin_inr": float, "waste_avoided_inr": float,
                        "discount_cost_inr": float, "ci_low": float, "ci_high": float },
  "guardrails_all_passed": bool,
  "updated_at": "<RFC3339>"
}
```
Source: `taal.plays` denormalised columns plus `JSON_VALUE(play_json, '$.expected_outcome...')`
and `JSON_VALUE(play_json, '$.guardrails')` reduced to a single boolean.

### `substitutes/{sku}`
```
{ "candidates": [string, ...], "updated_at": "<RFC3339>" }
```
Source: `taal.substitutes` verbatim. Stock filtering against live `stock/{node}/{sku}` happens in
the Customer Agent's `find_substitutes` tool at chat time, not in this mirror.

### `events/{run_id}/{seq}`
Agent trace events for the trace panel and replay (DECISIONS §10); one document per
`taal.execution_events` row, `seq` as the document id so the panel can range-query in order.

### `demo/`
Golden runs and the per-visitor reset snapshot (judge mode, DECISIONS §5.6): a fixed set of
documents cloned into a visitor's namespace on first load, never written by this nightly mirror.

## Freshness and ownership

- Every mirror write carries `updated_at`; the judge-mode health strip reads the most recent one
  to show "last Sense run N min at HH:MM" (DECISIONS §5.6).
- BigQuery is authoritative; if a mirror write fails partway, the next nightly run overwrites the
  same documents from BigQuery again -- there is no partial-write recovery logic in Firestore
  itself, by design (DECISIONS §17.1: the files are the contract, not incremental state).
- No LLM reads BigQuery at chat time (DECISIONS §18.2); everything the Customer Agent needs at
  chat time must be in this mirror or in Sessions.
