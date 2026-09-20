"""Planner Agent (ADK LlmAgent in a LoopAgent). `python -m agents.planner --gap <gap_id>`."""
from __future__ import annotations

# `adk eval agents/planner ...` (harness/run_evals.py, `make eval`) imports this package looking
# for `root_agent` here, not in agent.py directly -- found by actually running `adk eval` and
# reading its traceback ("Agent module should have either root_agent or get_agent_async"), not
# guessed. Re-exporting changes no behavior: everything that already builds the planner agent
# (run.py, tools) imports directly from .agent and is unaffected.
from .agent import root_agent  # noqa: F401
