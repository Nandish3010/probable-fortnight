"""Gemini-as-judge scorer for Planner rationale quality (DECISIONS §12, checklist item
"Rationale quality on the 15-item human-labelled subset").

Usage: python -m harness.rationale_judge --plays <play.json>... --out eval/raw/rationale_judge_<date>.json

For each play, sends its `rationale`, `citations`, `guardrails`, `expected_outcome` and
`target`/`mechanic` fields to Gemini on Vertex AI with the rubric below (structured output: one
score 1-5 plus a short justification per criterion), following the same
`genai.Client(vertexai=True)` + `response_schema` pattern already used in
`agents/capture/vision.py` and the same "build prompt, call Vertex, parse" shape as
`harness/spec_review.py`.

## Rubric ("rationale quality", four criteria, each scored 1 (fails) - 5 (excellent))

1. **cite_or_drop compliance** -- every number stated in the rationale (rupee amounts, unit
   counts, percentages, dates) must appear in, and be traceable to, `citations` or the play's own
   `expected_outcome`/`target`/`guardrails` fields (the numbers `cite_or_drop` itself checks
   against). A rationale inventing a number not backed by any cited source scores low regardless
   of how plausible the number sounds.
2. **Guardrail consistency** -- the rationale's stated reasoning must be consistent with which
   guardrails actually passed or failed on this play (`guardrails[].passed`/`detail`). A rationale
   that claims a margin/consent/holdout property the guardrail list contradicts, or that omits a
   guardrail failure the play's own record shows, scores low.
3. **No invented facts** -- beyond numbers (criterion 1), the rationale must not assert facts
   about the customer, product, or situation that are not supported by the gap/estimator/policy
   context available to it (e.g. inventing a customer complaint, a competitor action, or a policy
   clause that does not exist in the cited policy version).
4. **Operator actionability** -- a retail operator reading only the rationale (not the raw JSON)
   should be able to tell what is happening, why this mechanic over the alternatives, and what
   they are approving. Vague, generic, or template-sounding text that could apply to any play
   scores low even if technically not wrong.

Overall score = mean of the four criteria (1-5 scale). A play is judged as clearing the bar at
mean >= 4.0 (the same "genuinely more right than wrong, no fabrication" bar `cite_or_drop` itself
enforces deterministically for criterion 1; criteria 2-4 use the same threshold intentionally).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agents.gate.config import load_models

RESULT_SCHEMA = {
    "type": "OBJECT",
    "required": ["criteria", "overall_score", "overall_justification"],
    "properties": {
        "criteria": {
            "type": "OBJECT",
            "required": ["cite_or_drop_compliance", "guardrail_consistency", "no_invented_facts", "operator_actionability"],
            "properties": {
                name: {
                    "type": "OBJECT",
                    "required": ["score", "justification"],
                    "properties": {
                        "score": {"type": "INTEGER", "description": "1 (fails) to 5 (excellent)"},
                        "justification": {"type": "STRING", "description": "1-2 sentences, citing specific text from the rationale or play"},
                    },
                }
                for name in ("cite_or_drop_compliance", "guardrail_consistency", "no_invented_facts", "operator_actionability")
            },
        },
        "overall_score": {"type": "NUMBER", "description": "mean of the four criteria scores"},
        "overall_justification": {"type": "STRING", "description": "1-3 sentences summarising the verdict"},
    },
}

RUBRIC_PROMPT = """You are grading the RATIONALE field of one automatically-proposed retail
demand-shaping "play" (a discount/bundle/transfer action on at-risk inventory), for a system
called Taal. You are not grading whether the play itself is a good business decision -- you are
grading whether its written rationale is an honest, well-grounded, useful explanation of that
play, given everything else on the play object.

An empty, near-empty, or purely generic rationale that explains nothing specific about THIS play
must score 1 on every one of the four criteria below, not just operator_actionability. Do not
award a criterion a high score merely because there is no content in the rationale to contradict
it (e.g. "it cites no numbers so it cannot cite one wrongly" is NOT a 5 -- a rationale that gives
an operator nothing to act on has failed cite_or_drop_compliance, guardrail_consistency and
no_invented_facts too, precisely because it fails to do the job those criteria are checking for).

Score each of the four criteria 1 (fails) to 5 (excellent):

1. cite_or_drop_compliance: every number stated in the rationale (rupee amounts, unit counts,
   percentages, dates) must be traceable to the play's `citations`, `expected_outcome`,
   `counterfactuals`, `target`, `mechanic_params`, `audience`, `holdout`, `guardrails`, or
   `alternatives` fields below. The first seven are the exact field set the real deterministic
   `cite_or_drop` guardrail (`agents/gate/guardrails.py::cited_numbers`) checks against; note that
   guardrail does NOT currently walk `alternatives` (a real gap in that guardrail, not something
   to hold against the rationale) -- a rationale citing a rejected alternative's own real
   `expected_margin_inr`/`expected_units` when explaining why one mechanic beat another (e.g.
   "preferred over a transfer at X INR margin") is citing real play data, not inventing it, even
   though the deterministic guardrail does not itself check that field. Inventing a number that
   appears in none of these eight fields scores low.
2. guardrail_consistency: the rationale's reasoning must not contradict which guardrails actually
   passed or failed (see `guardrails` below). Claiming something a guardrail's own detail
   contradicts, or silently ignoring a guardrail failure, scores low.
3. no_invented_facts: beyond numbers, the rationale must not assert facts (customer complaints,
   competitor actions, policy clauses, audience segment identities) that are not supported by the
   play's own fields, the `audience_segment_names` mapping, or the `policy_text` below. A
   rationale citing a real numbered rule from `policy_text` (e.g. "policy v1, rule 2") is citing a
   real fact, not inventing one, as long as that rule number and its substance actually appear in
   `policy_text`. Likewise a segment's real name (e.g. "Tea connoisseurs" for a segment id in the
   audience) is a real fact, and a claim about a segment's mean affinity score (e.g. "mean affinity
   above 0.07") is a real fact if it is consistent with `audience_candidates` below (the same
   per-segment mean-affinity numbers the Planner's own tool context provided when drafting this
   play). Naming a policy rule not in `policy_text`, a segment not in this play's audience or the
   mapping, or an affinity threshold inconsistent with `audience_candidates`, would be invented.
   A node's real human-readable name (e.g. "Dark store 02 (North Bengaluru)" for node id DS-02,
   from `node_names` below) is also a real fact, not an invented one.
4. operator_actionability: a retail operator reading only the rationale text should understand
   what is happening, why this mechanic, and what they are approving. Generic/template-sounding
   text that could describe any play scores low.

## Play under review

Objective: {objective}
Mechanic: {mechanic} (params: {mechanic_params})
Target: {target}
Node names (node_id -> human-readable name, for the node_ids in `target` above): {node_names}
Audience: {audience}
Audience segment names (segment_id -> human-readable name, for the segment_ids in `audience` above): {audience_segment_names}
Audience candidates (the real per-segment reach/consent/mean-affinity numbers the Planner's `get_candidate_audiences` tool returned for this play's sku+node, before the Planner picked which segments to include): {audience_candidates}
Expected outcome: {expected_outcome}
Counterfactuals (do-nothing / blanket-markdown baselines the Estimator computed for this gap): {counterfactuals}
Alternatives (other mechanics the Planner considered and rejected, with their own real computed outcomes): {alternatives}
Guardrails: {guardrails}
Citations: {citations}
Policy version: {policy_version}
Policy text (the numbered rules the Planner's prompt included for this policy version): {policy_text}

## Rationale text to grade

\"\"\"{rationale}\"\"\"

Return your scores in the required structured format. Be specific in each justification: quote or
paraphrase the exact part of the rationale your score is about.
"""


def build_prompt(
    play: dict[str, Any],
    segment_names: dict[str, str] | None = None,
    policy_texts: dict[str, str] | None = None,
    audience_candidates: list[dict[str, Any]] | None = None,
    node_names: dict[str, str] | None = None,
) -> str:
    audience = play.get("audience", {})
    target = play.get("target", {})
    names = {sid: n for sid, n in (segment_names or {}).items() if sid in (audience.get("segment_ids") or [])}
    nnames = {nid: n for nid, n in (node_names or {}).items() if nid in (target.get("node_ids") or [])}
    policy_text = (policy_texts or {}).get(str(play.get("policy_version")), "(policy text not available to the judge for this policy_version)")
    return RUBRIC_PROMPT.format(
        objective=play.get("objective"),
        mechanic=play.get("mechanic"),
        mechanic_params=json.dumps(play.get("mechanic_params", {}), ensure_ascii=False),
        target=json.dumps(target, ensure_ascii=False),
        node_names=json.dumps(nnames, ensure_ascii=False),
        audience=json.dumps(audience, ensure_ascii=False),
        audience_segment_names=json.dumps(names, ensure_ascii=False),
        audience_candidates=json.dumps(audience_candidates if audience_candidates is not None else "(not computed for this play)", ensure_ascii=False),
        expected_outcome=json.dumps(play.get("expected_outcome", {}), ensure_ascii=False),
        counterfactuals=json.dumps(play.get("counterfactuals", {}), ensure_ascii=False),
        alternatives=json.dumps(play.get("alternatives", []), ensure_ascii=False),
        guardrails=json.dumps(play.get("guardrails", []), ensure_ascii=False),
        citations=json.dumps(play.get("citations", []), ensure_ascii=False),
        policy_version=play.get("policy_version"),
        policy_text=policy_text,
        rationale=play.get("rationale", ""),
    )


def judge_one(
    client: Any,
    model_id: str,
    play: dict[str, Any],
    segment_names: dict[str, str] | None = None,
    policy_texts: dict[str, str] | None = None,
    audience_candidates: list[dict[str, Any]] | None = None,
    node_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    import time

    from google.genai import types
    from google.genai.errors import ClientError

    prompt = build_prompt(play, segment_names, policy_texts, audience_candidates, node_names)
    for attempt in range(4):
        try:
            resp = client.models.generate_content(
                model=model_id,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=RESULT_SCHEMA, temperature=0.0),
            )
            break
        except ClientError as e:
            if e.code == 429 and attempt < 3:
                time.sleep(2 ** attempt * 5)  # 5s, 10s, 20s backoff on quota exhaustion
                continue
            raise
    result = json.loads(resp.text)
    return {"play_id": play.get("play_id"), "gap_id": play.get("gap_id"), "model_id": model_id, "judge_result": result}


def load_play(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    # accept either a bare play object, or a `run_planner_async` result ({"play": {...}, ...}),
    # or a fixture mutation wrapper ({"mutation": ..., "play": {...}})
    return obj["play"] if "play" in obj and "rationale" not in obj else obj


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plays", nargs="+", required=True, help="play JSON files (bare play object, or {play: {...}} wrapper)")
    ap.add_argument("--out", required=True, help="output JSON path (raw judge results)")
    ap.add_argument("--project", default=None, help="GCP project (default: $GOOGLE_CLOUD_PROJECT)")
    ap.add_argument("--segments", default=None, help="path to a segments.jsonl (segment_id, name) to ground audience segment names; omit to skip that context")
    ap.add_argument("--policy-v2-file", default=None, help="path to the v2 policy text (fixtures/policy_v2.txt); v1 is always loaded from the tenant config")
    ap.add_argument("--store", default=None, help="a data dir (e.g. .local/data) to re-derive get_candidate_audiences (real per-segment mean-affinity numbers) as extra judge context; read-only, never mutated")
    args = ap.parse_args(argv)

    import os

    project = args.project or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        print("rationale_judge: no GCP project (set GOOGLE_CLOUD_PROJECT or --project); this is a live-Vertex-only tool", file=sys.stderr)
        return 1

    from google import genai

    models = load_models()
    location = os.environ.get("GOOGLE_CLOUD_LOCATION") or models["vertex"]["location"]
    model_id = models["ids"]["flash"]
    client = genai.Client(vertexai=True, project=project, location=location)

    segment_names: dict[str, str] = {}
    if args.segments:
        for line in Path(args.segments).read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                segment_names[row["segment_id"]] = row["name"]

    from agents.gate.config import load_tenant

    tenant = load_tenant()
    policy_texts: dict[str, str] = {tenant.policy_version: tenant.policy_text}
    if args.policy_v2_file:
        policy_texts["v2"] = Path(args.policy_v2_file).read_text(encoding="utf-8")

    audience_ctx = None
    node_names: dict[str, str] = {}
    if args.store:
        # Read-only: PlannerContext.build + get_candidate_audiences only read the store (no write
        # path is exercised), so this is safe to point at a live tenant dir directly.
        from agents.planner import tools as pt
        from agents.planner.context import PlannerContext, set_context

        audience_ctx = PlannerContext.build(args.store, run_id="rationale_judge_probe", tenant=tenant)
        set_context(audience_ctx)
        nodes_file = Path(args.store) / "nodes.jsonl"
        if nodes_file.exists():
            for line in nodes_file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    node_names[row["node_id"]] = row["name"]

    def _candidates(play: dict[str, Any]) -> list[dict[str, Any]] | None:
        if audience_ctx is None:
            return None
        target = play.get("target") or {}
        sku, node_ids, gap_id = target.get("sku"), target.get("node_ids") or [], play.get("gap_id")
        if not sku or not node_ids:
            return None
        try:
            return pt.get_candidate_audiences(sku, node_ids, play.get("objective", ""), gap_id=gap_id)
        except Exception:  # noqa: BLE001 - a play whose gap/sku is not in this store just gets no extra context
            return None

    results = []
    for p in args.plays:
        play = load_play(Path(p))
        try:
            r = judge_one(client, model_id, play, segment_names, policy_texts, _candidates(play), node_names)
        except Exception as e:  # noqa: BLE001 - a single bad call should not kill the whole batch
            r = {"play_id": play.get("play_id"), "gap_id": play.get("gap_id"), "error": f"{type(e).__name__}: {e}"}
        results.append(r)
        print(f"{r.get('play_id')}: {r.get('judge_result', {}).get('overall_score', 'ERROR')}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"model_id": model_id, "location": location, "n": len(results), "results": results}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
