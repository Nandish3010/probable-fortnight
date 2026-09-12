"""Gemini Live session configuration for the phone view (DECISIONS §5.1). Stub: config only."""
from __future__ import annotations

from typing import Any

from agents.gate.config import load_models

SYSTEM_INSTRUCTION = (
    "You are the Kutumb Mart operations assistant for a dark-store manager. Answer in the manager's language "
    "(Kannada or English). Use the tools for every fact: gaps from get_gaps, play details from explain_play. "
    "Never approve a play without ask_confirmation returning yes."
)
TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {"name": "get_gaps", "description": "Open gaps at a node ranked by rupees at stake.", "parameters": {"type": "object", "properties": {"node_id": {"type": "string"}}, "required": ["node_id"]}},
    {"name": "explain_play", "description": "One-paragraph spoken summary of a play.", "parameters": {"type": "object", "properties": {"play_id": {"type": "string"}}, "required": ["play_id"]}},
    {"name": "approve_play", "description": "Approve a play (calls POST /approve).", "parameters": {"type": "object", "properties": {"play_id": {"type": "string"}}, "required": ["play_id"]}},
    {"name": "ask_confirmation", "description": "Ask the manager a yes/no question and return the answer.", "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}},
]


def live_config() -> dict[str, Any]:
    models = load_models()
    return {"model": models["ids"]["live"], "system_instruction": SYSTEM_INSTRUCTION, "tools": TOOL_DECLARATIONS, "languages": ["kn-IN", "en-IN"], "status": "stub: not connected in this build"}
