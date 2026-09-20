"""Scripted stand-in for Gemini used when TAAL_MODEL_BACKEND=stub (CI, fixtures, judge-mode replay).

It is an ADK `BaseLlm`, so the LlmAgent, LoopAgent, tools, session state, escalation and event
log are the real thing; only the decision policy is a script. `get_gap`, `get_candidate_audiences`
and `get_past_plays` are no longer called: run.py fetches them up front (deterministic reads) and
embeds the results as a fenced JSON block in the initial user message -- this script reads that
block the way prompts/planner.md tells Gemini to, instead of issuing a tool call for it. It then
estimates every candidate in one `estimate_outcomes` call and tries `propose_play` on candidates
in policy order, ending its turn with text when a guardrail fails (so the LoopAgent can iterate)
or when the proposal is accepted.
"""
from __future__ import annotations

import json
import re
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types

from . import drafting

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

    def _alt(self, c: dict[str, Any], est: dict[str, Any], why: str) -> dict[str, Any]:
        return {"mechanic": c["mechanic"], "mechanic_params": c.get("mechanic_params", {}), "expected_units": est["expected_outcome"]["units"], "expected_margin_inr": est["expected_outcome"]["margin_inr"], "rejected_because": why[:400]}

    def _with_estimate(self, draft: dict[str, Any], est: dict[str, Any], gap: dict[str, Any], audiences: list[dict[str, Any]], rejected: list[dict[str, Any]]) -> dict[str, Any]:
        return drafting.finish_draft(draft, gap, est, audiences, rejected, self.policy_text)
