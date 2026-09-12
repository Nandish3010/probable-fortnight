"""The 20 scripted conversations under fixtures/conversations run against the stub Customer Agent in a
sandbox. `__TREATED_EN__` / `__HOLDOUT__` are resolved from the approved play's assignments."""
import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest

from agents.customer.chat import ENVELOPE_SCHEMA, reset_sessions, run_chat_async
from agents.gate.config import load_tenant
from services.api.approve import approve

ROOT = Path(__file__).resolve().parents[2]
CONVOS = sorted((ROOT / "fixtures" / "conversations").glob("*.json"))
NOW = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)


def _resolve(customer_id: str, sandbox, play_id: str | None) -> str:
    if not customer_id.startswith("__"):
        return customer_id
    assert play_id, "placeholder customers need an approved play"
    lang = {c["customer_id"]: c.get("language") for c in sandbox.read("customers")}
    rows = [a for a in sandbox.read("play_assignments") if a["play_id"] == play_id]
    if customer_id == "__HOLDOUT__":
        return next(a["customer_id"] for a in rows if a["arm"] == "holdout")
    return next(a["customer_id"] for a in rows if a["arm"] == "treated" and lang.get(a["customer_id"]) == "en")


@pytest.mark.parametrize("path", CONVOS, ids=[p.stem for p in CONVOS])
def test_conversation(path: Path, sandbox):
    convo = json.loads(path.read_text(encoding="utf-8"))
    reset_sessions()
    play_id = convo["setup"].get("approve_play")
    if play_id:
        approve(sandbox, load_tenant(), play_id, NOW)
    cid = _resolve(convo["customer_id"], sandbox, play_id)
    session = f"{cid}:web"
    import asyncio

    for turn in convo["turns"]:
        env = asyncio.run(run_chat_async(sandbox, session, turn["text"], now_iso="2026-09-12T09:05:00Z"))[0]
        jsonschema.validate(env, ENVELOPE_SCHEMA, format_checker=jsonschema.FormatChecker())
        exp = turn["expect"]
        called = [t["name"] for t in env["tool_calls"] if "args" in t]
        text = env["text"]
        if "contains_any" in exp:
            assert any(s in text for s in exp["contains_any"]), (text, exp["contains_any"])
        for s in exp.get("not_contains", []):
            assert s not in text, text
        for t in exp.get("tool_called", []):
            assert t in called, (t, called)
        if exp.get("buttons_min"):
            assert len(env.get("buttons") or []) >= exp["buttons_min"]
        if exp.get("buttons_max"):
            assert len(env.get("buttons") or []) <= exp["buttons_max"]
        if exp.get("list_rows_min"):
            assert len((env.get("list") or {}).get("rows") or []) >= exp["list_rows_min"], env.get("list")
        if exp.get("list_rows_max"):
            assert len((env.get("list") or {}).get("rows") or []) <= exp["list_rows_max"]
        if exp.get("citation_type"):
            assert any(c["type"] == exp["citation_type"] for c in env.get("citations") or []), env.get("citations")
        if exp.get("no_offer"):
            assert not any(c["type"] == "play" for c in env.get("citations") or [])
            assert "add:" not in json.dumps(env.get("buttons") or [])
        if exp.get("order_with_play"):
            lines = [ln for ln in sandbox.read("order_lines") if ln["customer_id"] == cid and ln.get("play_id") == exp["order_with_play"]]
            assert lines, "order line must carry the play_id"
        if exp.get("order_without_play"):
            lines = [ln for ln in sandbox.read("order_lines") if ln["customer_id"] == cid and ln["ts"] == "2026-09-12T09:05:00Z"]
            assert lines and all(not ln.get("play_id") for ln in lines)
        if exp.get("consent_withdrawn"):
            rows = [r for r in sandbox.read("consent") if r["customer_id"] == cid and r["channel"] == "web_chat"]
            assert rows and all(r.get("withdrawn_at") for r in rows)
        if exp.get("latest_line_no_play"):
            mine = [ln for ln in sandbox.read("order_lines") if ln["customer_id"] == cid]
            assert mine and not mine[-1].get("play_id") and float(mine[-1]["discount"]) == 0.0
        if exp.get("refused"):
            assert "ORD-" not in text
        if exp.get("latency_recorded"):
            assert isinstance(env.get("latency_ms"), int) and env["latency_ms"] >= 0


def test_twenty_conversations_exist():
    assert len(CONVOS) >= 20
