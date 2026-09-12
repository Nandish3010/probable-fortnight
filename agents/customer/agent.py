"""Customer Agent: ADK `LlmAgent` with six tools (DECISIONS §5.5). Model from config/models.toml."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.models.registry import LLMRegistry
from google.genai import types

from agents.gate.config import load_models

from .stub_llm import StubCustomerLlm
from .tools import TOOLS

# The scripted stub models report no token usage; ADK logs that on every turn. Quiet it.
logging.getLogger("google_adk.google.adk.telemetry._metrics").setLevel(logging.ERROR)

PROMPT = Path(__file__).resolve().parent / "prompts" / "customer.md"
LLMRegistry.register(StubCustomerLlm)


def build_customer_agent(catalog: dict[str, str], backend: str | None = None) -> LlmAgent:
    models = load_models()
    backend = backend or models["backend"]
    if backend == "stub":
        model = StubCustomerLlm(catalog=catalog)
    elif backend == "vertex":
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
        if models["vertex"].get("location") and not os.environ.get("GOOGLE_CLOUD_LOCATION"):
            os.environ["GOOGLE_CLOUD_LOCATION"] = models["vertex"]["location"]
        model = models["ids"]["flash"]
    else:
        raise ValueError(f"unknown TAAL_MODEL_BACKEND {backend!r}")
    catalogue_lines = "\n".join(f"- {name}: {sku}" for name, sku in sorted(catalog.items())[:400])
    instruction = PROMPT.read_text(encoding="utf-8") + "\n\n## Catalogue (name: sku)\n" + catalogue_lines + "\n"
    return LlmAgent(
        name="customer",
        description="Kutumb Mart web-chat assistant grounded in node stock, offers and consent.",
        model=model,
        instruction=instruction,
        tools=list(TOOLS),
        generate_content_config=types.GenerateContentConfig(temperature=0.3),
    )
