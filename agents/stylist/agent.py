"""Stylist Agent: ADK `LlmAgent` with six tools (DECISIONS §5.9). Model from config/models.toml."""
from __future__ import annotations

import logging
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.models.registry import LLMRegistry
from google.genai import types

from agents.chat_runtime import vertex_env
from agents.gate.config import load_models

from .stub_llm import StubStylistLlm
from .tools import TOOLS

logging.getLogger("google_adk.google.adk.telemetry._metrics").setLevel(logging.ERROR)

PROMPT = Path(__file__).resolve().parent / "prompts" / "stylist.md"
LLMRegistry.register(StubStylistLlm)


def build_stylist_agent(apparel: dict[str, dict], backend: str | None = None) -> LlmAgent:
    models = load_models()
    backend = backend or models["backend"]
    if backend == "stub":
        model = StubStylistLlm(apparel=apparel)
    elif backend == "vertex":
        vertex_env(models)
        model = models["ids"]["flash"]
    else:
        raise ValueError(f"unknown TAAL_MODEL_BACKEND {backend!r}")
    catalogue_lines = "\n".join(f"- {p['name']}: {sku} ({p['role']}, {p['colour_family']})" for sku, p in sorted(apparel.items())[:400])
    instruction = PROMPT.read_text(encoding="utf-8") + "\n\n## Catalogue (name: sku (role, colour family))\n" + catalogue_lines + "\n"
    return LlmAgent(
        name="stylist",
        description="Kutumb Mart style assistant grounded in apparel stock at the customer's store.",
        model=model,
        instruction=instruction,
        tools=list(TOOLS),
        generate_content_config=types.GenerateContentConfig(temperature=0.3),
    )
