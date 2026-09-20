"""The Planner: an ADK `LlmAgent` inside a `LoopAgent` (max 3 iterations, DECISIONS §5.3).

The loop exits when `propose_play` escalates (guardrails_all_passed = true in session state);
otherwise the failure detail is in the transcript and the next iteration revises. The model comes
from config/models.toml: `stub` builds a StubPlannerLlm, `vertex` uses the pinned Gemini ID via
Vertex AI (GOOGLE_GENAI_USE_VERTEXAI=TRUE, project and location from the environment).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from google.adk.agents import LlmAgent, LoopAgent
from google.adk.models import BaseLlm
from google.adk.models.registry import LLMRegistry
from google.genai import types

from agents.gate.config import TenantConfig, load_models, load_tenant

from .stub_llm import StubPlannerLlm
from .tools import TOOLS

# The scripted stub models report no token usage; ADK logs that on every turn. Quiet it.
logging.getLogger("google_adk.google.adk.telemetry._metrics").setLevel(logging.ERROR)

PROMPT = Path(__file__).resolve().parent / "prompts" / "planner.md"
MAX_ITERATIONS = 3
LLMRegistry.register(StubPlannerLlm)


def _vertex_model_id(models: dict) -> str:
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    if models["vertex"].get("location") and not os.environ.get("GOOGLE_CLOUD_LOCATION"):
        os.environ["GOOGLE_CLOUD_LOCATION"] = models["vertex"]["location"]
    return models["ids"]["flash"]


def build_model(tenant: TenantConfig, policy_text: str, run_id: str, as_of: str, backend: str | None = None) -> str | BaseLlm:
    models = load_models()
    backend = backend or models["backend"]
    if backend == "stub":
        return StubPlannerLlm(
            holdout_fraction=float(tenant.thresholds.get("default_holdout_fraction", 0.10)),
            min_treated_n=int(tenant.thresholds.get("min_treated_n", 20)),
            languages=list(tenant.languages), as_of=as_of, run_id=run_id, policy_text=policy_text,
        )
    if backend == "vertex":
        return _vertex_model_id(models)
    raise ValueError(f"unknown TAAL_MODEL_BACKEND {backend!r}")


def build_planner(tenant: TenantConfig, policy_text: str, policy_version: str, run_id: str, as_of: str, backend: str | None = None) -> LoopAgent:
    instruction = PROMPT.read_text(encoding="utf-8") + f"\n\n## Policy {policy_version}\n{policy_text.strip()}\n"
    models = load_models()
    thinking = models.get("thinking", {}).get("planner_final", "medium")
    config = types.GenerateContentConfig(temperature=0.2)
    if (backend or models["backend"]) == "vertex":
        model_id = models["ids"]["flash"]
        try:
            if model_id.startswith("gemini-3"):
                config.thinking_config = types.ThinkingConfig(thinking_level=thinking)  # type: ignore[attr-defined]
            else:
                # Gemini 2.5 rejects thinking_level outright (400 INVALID_ARGUMENT); it takes a
                # token budget instead. 0 disables thinking on 2.5 Flash.
                config.thinking_config = types.ThinkingConfig(thinking_budget={"low": 0, "medium": 1024, "high": 4096}.get(thinking, 1024))
        except Exception:  # older google-genai without ThinkingConfig: keep default
            pass
    planner = LlmAgent(
        name="planner",
        description="Designs one demand-shaping play for a supply gap under the tenant policy.",
        model=build_model(tenant, policy_text, run_id, as_of, backend),
        instruction=instruction,
        tools=list(TOOLS),
        generate_content_config=config,
    )
    return LoopAgent(name="planner_loop", description="Plan, check guardrails, revise up to three times.", sub_agents=[planner], max_iterations=MAX_ITERATIONS)


def _default_root_agent() -> LoopAgent:
    """Agent for `adk eval agents/planner` and `adk web`: tenant policy v1, stub or vertex per config."""
    from datetime import date

    tenant = load_tenant()
    return build_planner(tenant, tenant.policy_text, tenant.policy_version, "adk-cli", date.today().isoformat())


root_agent = _default_root_agent()
