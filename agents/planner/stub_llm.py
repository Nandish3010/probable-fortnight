"""Scripted stand-in for Gemini used when TAAL_MODEL_BACKEND=stub (CI, fixtures, judge-mode replay).

It is an ADK `BaseLlm`, so the LlmAgent, LoopAgent, tools, session state, escalation and event
log are the real thing; only the decision policy is a script. It reads the transcript, decides the
next tool call the way prompts/planner.md tells Gemini to, and ends its turn with text when a
guardrail fails (so the LoopAgent can iterate) or when the proposal is accepted.
"""
from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types

from . import drafting

GAP_RE = re.compile(r"gap_id=(gap_[A-Za-z0-9_-]+)")
POLICY_RE = re.compile(r"policy_version=([A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)")


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

    def _call(self, name: str, args: dict[str, Any]) -> LlmResponse:
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))]))

    def _say(self, text: str) -> LlmResponse:
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        yield self.decide(llm_request)

    def decide(self, req: LlmRequest) -> LlmResponse:
        t = self._transcript(req)
        m = GAP_RE.search(t["user_text"])
        if not m:
            return self._say("I need a gap_id=<id> to plan.")
        gap_id = m.group(1)
        pv = POLICY_RE.search(t["user_text"])
        policy_version = pv.group(1) if pv else "v1"
        by_name: dict[str, list[dict[str, Any]]] = {}
        for name, resp in t["responses"]:
            by_name.setdefault(name, []).append(resp)
        gap = (by_name.get("get_gap") or [None])[0]
        if gap is None:
            return self._call("get_gap", {"gap_id": gap_id})
        if "error" in gap and "gap_id" not in gap:
            return self._say(f"Cannot plan: {gap['error']}")
        audiences = (by_name.get("get_candidate_audiences") or [None])[0]
        if audiences is None:
            return self._call("get_candidate_audiences", {"sku": gap["sku"], "node_ids": [gap["node_id"]], "objective": drafting.OBJECTIVE_BY_GAP[gap["type"]]})
        audiences = audiences.get("result", audiences) if isinstance(audiences, dict) else audiences
        candidates = drafting.candidate_mechanics(gap, self.policy_text)
        if not candidates:
            return self._say("No admissible mechanic for this gap under the current policy; escalate to a human.")
        if "get_past_plays" not in by_name:
            return self._call("get_past_plays", {"sku": gap["sku"], "category": (gap.get("product") or {}).get("category", ""), "mechanic": candidates[0]["mechanic"]})
        # pair estimate calls with responses in order
        est_calls = [args for name, args in t["calls"] if name == "estimate_outcome"]
        est_resps = by_name.get("estimate_outcome", [])
        estimates = {drafting.draft_key(a["play_draft"]): r for a, r in zip(est_calls, est_resps, strict=False)}
        drafts = {drafting.draft_key(c): drafting.build_draft(gap, audiences, c, policy_version, self.run_id, self.holdout_fraction, self.min_treated_n, self.languages, self.as_of) for c in candidates}
        for c in candidates:
            k = drafting.draft_key(c)
            if k not in estimates:
                return self._call("estimate_outcome", {"play_draft": drafts[k]})
        check_calls = [args for name, args in t["calls"] if name == "check_guardrails"]
        check_resps = by_name.get("check_guardrails", [])
        checks = {drafting.draft_key(a["play_draft"]): r for a, r in zip(check_calls, check_resps, strict=False)}
        prop_calls = [args for name, args in t["calls"] if name == "propose_play"]
        prop_resps = by_name.get("propose_play", [])
        proposals = {drafting.draft_key(a["play"]): r for a, r in zip(prop_calls, prop_resps, strict=False)}
        if proposals and list(proposals.values())[-1].get("valid"):
            return self._say(f"DONE {list(proposals.values())[-1]['play_id']}")
        rejected: list[dict[str, Any]] = []
        for c in candidates:
            k = drafting.draft_key(c)
            est = estimates[k]
            chk = checks.get(k)
            prop = proposals.get(k)
            if prop is not None and not prop.get("valid"):
                rejected.append(self._alt(c, est, "; ".join(prop.get("errors") or ["rejected"])))
                continue
            if chk is None:
                return self._call("check_guardrails", {"play_draft": self._with_estimate(drafts[k], est, gap, audiences, rejected)})
            if not chk.get("all_passed"):
                failed = [r for r in chk["results"] if not r["passed"]]
                rejected.append(self._alt(c, est, "; ".join(f"{r['rule']}: {r['detail']}" for r in failed)))
                last_check_key = drafting.draft_key(check_calls[-1]["play_draft"]) if check_calls else None
                if last_check_key == k and t["last"] == "response":
                    # the failure is the newest thing in the transcript: end the iteration so the loop can revise
                    return self._say("Guardrail failed: " + "; ".join(f"{r['rule']} ({r['detail']})" for r in failed) + ". Revising the play.")
                continue
            play = self._with_estimate(drafts[k], est, gap, audiences, rejected)
            play["guardrails"] = chk["results"]
            return self._call("propose_play", {"play": play})
        return self._say("No candidate passed the guardrails within the loop budget; escalate to a human.")

    def _alt(self, c: dict[str, Any], est: dict[str, Any], why: str) -> dict[str, Any]:
        return {"mechanic": c["mechanic"], "mechanic_params": c.get("mechanic_params", {}), "expected_units": est["expected_outcome"]["units"], "expected_margin_inr": est["expected_outcome"]["margin_inr"], "rejected_because": why[:400]}

    def _with_estimate(self, draft: dict[str, Any], est: dict[str, Any], gap: dict[str, Any], audiences: list[dict[str, Any]], rejected: list[dict[str, Any]]) -> dict[str, Any]:
        return drafting.finish_draft(draft, gap, est, audiences, rejected, self.policy_text)
