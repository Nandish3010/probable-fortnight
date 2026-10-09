# Agents

| Package | What | Spec | Checklist | Run |
|---|---|---|---|---|
| `gate/` | Deterministic estimator, eight guardrails, holdout assignment, sell-by rule, config, local store | §2.5, §3.4, §5.4 | `harness/checklists/estimator_gate.md` | `make unit` |
| `planner/` | ADK `LlmAgent` in a `LoopAgent` (max 3) with six tools; stub model for CI, Gemini via Vertex in production; Cost Governor | §5.3, §18.2 | `harness/checklists/planner_agent.md` | `python -m agents.planner --gap gap_chips_ds07` |
| `customer/` | ADK `LlmAgent` with six tools; orders through the MCP mock; JSON chat envelope | §5.5 | `harness/checklists/customer_agent.md` | `make agents` |
| `mcp_orders/` | MCP order mock (`mcp` 2.x `MCPServer`); in-memory session by default, stdio via `python -m agents.mcp_orders` | §5.5 | `harness/checklists/customer_agent.md` | `pytest tests/agents/test_mcp_orders.py` |
| `capture/` | Vision intake with confirmation questions and two-pass reading; voice session config (stub) | §5.1 | `harness/checklists/vision_intake.md`, `voice.md` | `POST /capture` |

`TAAL_MODEL_BACKEND=stub` (default) runs every agent on scripted models so the ADK plumbing,
tools, session state, escalation and event log are exercised without a network. `vertex` switches
to the pinned Gemini IDs in `config/models.toml` (needs `GOOGLE_CLOUD_PROJECT`).
