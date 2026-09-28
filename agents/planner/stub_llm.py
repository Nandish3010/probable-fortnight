"""Scripted stand-in for Gemini used when TAAL_MODEL_BACKEND=stub (CI, fixtures, judge-mode replay).

It is an ADK `BaseLlm`, so the LlmAgent, LoopAgent, tools, session state, escalation and event
log are the real thing; only the decision policy is a script. `get_gap`, `get_candidate_audiences`
and `get_past_plays` are no longer called: run.py fetches them up front (deterministic reads) and
embeds the results as a fenced JSON block in the initial user message -- this script reads that
block the way prompts/planner.md tells Gemini to, instead of issuing a tool call for it. It then
estimates every candidate in one `estimate_outcomes` call and tries `propose_play` on candidates
in policy order, ending its turn with text when a guardrail fails (so the LoopAgent can iterate)
or when the proposal is accepted.

Replay mode (TAAL_STUB_TRAJECTORY=recorded; off by default): for a gap whose evalset under
agents/planner/evalsets/ (or TAAL_STUB_TRAJECTORY_DIR) was built from a recorded real-model run
(harness/build_fixtures.py, marker "source=recorded_trace"), the stub issues the recorded tool names
in the recorded order instead of its own script -- same count, same positions, each recorded
propose_play rejection reproduced with a deliberately incomplete play -- then ends with the
recorded final text. It is the CI stand-in for the evalsets: with it on, `make eval` in stub mode
checks the harness and the tools against the real model's shape; it cannot say anything about
whether the model still behaves that way (only the vertex run of `make eval` does). Gaps without
a recorded evalset keep the scripted behaviour.
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types

from . import drafting

TRACE_MARKER = "source=recorded_trace"
EVALSETS = Path(__file__).resolve().parent / "evalsets"


def recorded_trajectory(gap_id: str) -> dict[str, Any] | None:
    """{tools, verdicts, final_text} from the gap's recorded-trace evalset, or None when replay is
    off or the gap has none."""
    if os.environ.get("TAAL_STUB_TRAJECTORY", "") != "recorded":
        return None
    path = Path(os.environ.get("TAAL_STUB_TRAJECTORY_DIR") or EVALSETS) / f"{gap_id}.evalset.json"
    if not path.exists():
        return None
    es = json.loads(path.read_text(encoding="utf-8"))
    if TRACE_MARKER not in es.get("description", ""):
        return None
    inv = es["eval_cases"][0]["conversation"][0]
    data = inv["intermediate_data"]
    return {
        "tools": [t["name"] for t in data.get("tool_uses") or []],
        "verdicts": [bool((r.get("response") or {}).get("valid")) for r in data.get("tool_responses") or [] if r.get("name") == "propose_play"],
        "final_text": "".join(p.get("text", "") for p in (inv.get("final_response") or {}).get("parts") or []),
    }

POLICY_RE = re.compile(r"policy_version=([A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)")
CONTEXT_RE = re.compile(r"```json\n(.*)\n```", re.S)


def _text(parts: list[types.Part] | None) -> str:
    return "".join(p.text or "" for p in (parts or []) if p.text)


class StubPlannerLlm(BaseLlm):
    model: str = "stub-planner"
    holdout_fraction: float = 0.10
    min_treated_n: int = 20
    languages: list[str] = ["en", "kn"]
    as_of: str = "2026-09-12"
    run_id: str = "run"
    policy_text: str = ""

    @classmethod
    def supported_models(cls) -> list[str]:
        return [r"stub-planner.*"]

    def _transcript(self, req: LlmRequest) -> dict[str, Any]:
        user_text, calls, responses, last = "", [], [], "user"
        for c in req.contents:
            for part in c.parts or []:
                if part.text and c.role == "user" and not user_text:
                    user_text = part.text
                elif part.text and c.role == "model":
                    last = "model_text"
                if part.function_call:
                    calls.append((part.function_call.name, dict(part.function_call.args or {})))
                    last = "call"
                if part.function_response:
                    responses.append((part.function_response.name, dict(part.function_response.response or {})))
                    last = "response"
        return {"user_text": user_text, "calls": calls, "responses": responses, "last": last}

    def _parse_context(self, user_text: str) -> dict[str, Any] | None:
        m = CONTEXT_RE.search(user_text)
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            return None

    def _call(self, name: str, args: dict[str, Any]) -> LlmResponse:
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))]))

    def _say(self, text: str) -> LlmResponse:
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        yield self.decide(llm_request)

    def decide(self, req: LlmRequest) -> LlmResponse:
        t = self._transcript(req)
        context = self._parse_context(t["user_text"])
        if context is None:
            return self._say("I need a gap_id=<id> to plan.")
        gap = context["gap"]
        if "error" in gap and "gap_id" not in gap:
            return self._say(f"Cannot plan: {gap['error']}")
        audiences = context["candidate_audiences"]
        pv = POLICY_RE.search(t["user_text"])
        policy_version = pv.group(1) if pv else "v1"
        candidates = drafting.candidate_mechanics(gap, self.policy_text)
        if not candidates:
            return self._say("No admissible mechanic for this gap under the current policy; escalate to a human.")
        drafts = {drafting.draft_key(c): drafting.build_draft(gap, audiences, c, policy_version, self.run_id, self.holdout_fraction, self.min_treated_n, self.languages, self.as_of) for c in candidates}

        by_name: dict[str, list[dict[str, Any]]] = {}
        for name, resp in t["responses"]:
            by_name.setdefault(name, []).append(resp)

        recorded = recorded_trajectory(gap.get("gap_id", ""))
        if recorded is not None:
            return self._replay(recorded, t, gap, audiences, candidates, drafts, by_name)

        est_resps = by_name.get("estimate_outcomes", [])
        if not est_resps:
            return self._call("estimate_outcomes", {"play_drafts": [drafts[drafting.draft_key(c)] for c in candidates]})
        estimates_list = est_resps[0]
        estimates_list = estimates_list.get("result", estimates_list) if isinstance(estimates_list, dict) else estimates_list
        estimates = {drafting.draft_key(c): estimates_list[i] for i, c in enumerate(candidates)}

        prop_calls = [args for name, args in t["calls"] if name == "propose_play"]
        prop_resps = by_name.get("propose_play", [])
        proposals = {drafting.draft_key(a["play"]): r for a, r in zip(prop_calls, prop_resps, strict=False)}
        if proposals and list(proposals.values())[-1].get("valid"):
            return self._say(f"DONE {list(proposals.values())[-1]['play_id']}")

        rejected: list[dict[str, Any]] = []
        for c in candidates:
            k = drafting.draft_key(c)
            est = estimates[k]
            prop = proposals.get(k)
            if prop is not None and not prop.get("valid"):
                errors = prop.get("errors") or ["rejected"]
                detail = "; ".join(e[len("guardrail "):] if e.startswith("guardrail ") else e for e in errors)
                rejected.append(self._alt(c, est, detail))
                last_prop_key = drafting.draft_key(prop_calls[-1]["play"]) if prop_calls else None
                if last_prop_key == k and t["last"] == "response":
                    # the failure is the newest thing in the transcript: end the iteration so the loop can revise
                    return self._say(f"Guardrail failed: {detail}. Revising the play.")
                continue
            if prop is None:
                if "error" in est:
                    continue
                play = self._with_estimate(drafts[k], est, gap, audiences, rejected)
                return self._call("propose_play", {"play": play})
        return self._say("No candidate passed the guardrails within the loop budget; escalate to a human.")

    def _replay(self, rec: dict[str, Any], t: dict[str, Any], gap: dict[str, Any], audiences: list[dict[str, Any]], candidates: list[dict[str, Any]], drafts: dict[str, dict[str, Any]], by_name: dict[str, list[dict[str, Any]]]) -> LlmResponse:
        made = [name for name, _ in t["calls"]]
        expected = rec["tools"]
        if made != expected[: len(made)]:
            return self._say(f"Replay diverged from the recorded trajectory at call {len(made) + 1}: made {made}, recorded {expected}")
        got = [bool(r.get("valid")) for r in by_name.get("propose_play", [])]
        if got != rec["verdicts"][: len(got)]:
            # e.g. the one play meant to be accepted was rejected: never paper over it with the recorded DONE
            return self._say(f"Replay diverged from the recorded propose_play verdicts: got {got}, recorded {rec['verdicts']}")
        if len(made) >= len(expected):
            return self._say(rec["final_text"])
        name = expected[len(made)]
        est_resps = by_name.get("estimate_outcomes", [])
        estimates: dict[str, dict[str, Any]] = {}
        if est_resps:
            first = est_resps[0].get("result", est_resps[0]) if isinstance(est_resps[0], dict) else est_resps[0]
            estimates = {drafting.draft_key(c): first[i] for i, c in enumerate(candidates) if i < len(first)}

        def play_for(c: dict[str, Any]) -> dict[str, Any]:
            k = drafting.draft_key(c)
            est = estimates.get(k)
            if est is None or "error" in est:
                return drafts[k]
            return self._with_estimate(drafts[k], est, gap, audiences, [])

        if name == "estimate_outcomes":
            return self._call(name, {"play_drafts": [drafts[drafting.draft_key(c)] for c in candidates]})
        if name == "get_gap":
            return self._call(name, {"gap_id": gap["gap_id"]})
        if name == "get_candidate_audiences":
            return self._call(name, {"sku": gap["sku"], "node_ids": [gap["node_id"]], "objective": drafting.OBJECTIVE_BY_GAP[gap["type"]], "gap_id": gap["gap_id"]})
        if name == "get_past_plays":
            return self._call(name, {"sku": gap["sku"], "category": (gap.get("product") or {}).get("category", ""), "mechanic": candidates[0]["mechanic"]})
        if name == "check_guardrails":
            return self._call(name, {"play_draft": play_for(candidates[0])})
        if name == "propose_play":
            n_prop = made.count("propose_play")
            should_pass = rec["verdicts"][n_prop] if n_prop < len(rec["verdicts"]) else True
            if not should_pass:
                bad = dict(play_for(candidates[0]))
                bad.pop("citations", None)  # schema-invalid on purpose: reproduces a recorded rejection
                return self._call(name, {"play": bad})
            return self._call(name, {"play": self._passing_play(candidates, play_for)})
        return self._say(f"Replay cannot issue recorded tool {name!r}")

    def _passing_play(self, candidates: list[dict[str, Any]], play_for) -> dict[str, Any]:
        """The first candidate in policy order whose finished play clears the guardrails (checked
        directly, so the one recorded accepted propose_play is not spent on a known failure)."""
        from .tools import check_guardrails

        plays = [play_for(c) for c in candidates]
        for play in plays:
            if play.get("expected_outcome") and check_guardrails(play).get("all_passed"):
                return play
        return plays[0]

    def _alt(self, c: dict[str, Any], est: dict[str, Any], why: str) -> dict[str, Any]:
        return {"mechanic": c["mechanic"], "mechanic_params": c.get("mechanic_params", {}), "expected_units": est["expected_outcome"]["units"], "expected_margin_inr": est["expected_outcome"]["margin_inr"], "rejected_because": why[:400]}

    def _with_estimate(self, draft: dict[str, Any], est: dict[str, Any], gap: dict[str, Any], audiences: list[dict[str, Any]], rejected: list[dict[str, Any]]) -> dict[str, Any]:
        return drafting.finish_draft(draft, gap, est, audiences, rejected, self.policy_text)
