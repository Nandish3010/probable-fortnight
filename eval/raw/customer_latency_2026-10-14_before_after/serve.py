"""Run services.api.main:app with per-turn instrumentation, for the before/after latency runs.

    cd <worktree>; PYTHONPATH=<worktree> TAAL_LAT_EVENTS=<events.jsonl> python <this file> <port>

Changes no app behaviour: it wraps (1) every Gemini generate_content_async call (model id actually
asked, model_version actually answering, token usage, function-call names, wall time), (2) every
Model Armor HTTP screen (wall time), and (3) services.api.main._screened_chat (turn counter, wall
time), and appends one JSON line per event to TAAL_LAT_EVENTS. The same file serves both runs.
"""
import itertools
import json
import os
import sys
import time

import uvicorn
from google.adk.models import google_llm

from services.api import main, model_armor

EVENTS = os.environ["TAAL_LAT_EVENTS"]
turn_ids = itertools.count(1)
current = {"turn": 0}


def emit(**kw):
    with open(EVENTS, "a", encoding="utf-8") as f:
        f.write(json.dumps({"turn": current["turn"], "ts": time.time(), **kw}) + "\n")


_orig_gen = google_llm.Gemini.generate_content_async


async def gen(self, llm_request, stream=False):
    t0 = time.perf_counter()
    last = None
    calls = []
    async for r in _orig_gen(self, llm_request, stream):
        last = r
        for p in (r.content.parts if r.content and r.content.parts else []):
            if p.function_call:
                calls.append(p.function_call.name)
        yield r
    u = getattr(last, "usage_metadata", None)
    emit(kind="model", asked=self.model, answered=getattr(last, "model_version", None), dt=round(time.perf_counter() - t0, 4),
         tok_in=getattr(u, "prompt_token_count", None) or 0, tok_out=getattr(u, "candidates_token_count", None) or 0,
         tok_think=getattr(u, "thoughts_token_count", None) or 0, tok_cached=getattr(u, "cached_content_token_count", None) or 0,
         fn_calls=calls, thinking=str(getattr(getattr(llm_request.config, "thinking_config", None), "thinking_level", None)))


google_llm.Gemini.generate_content_async = gen

_orig_call = model_armor._call


def timed_call(method, payload, tmpl, client=None):
    t0 = time.perf_counter()
    v = _orig_call(method, payload, tmpl, client)
    emit(kind="armor", method=method, dt=round(time.perf_counter() - t0, 4), source=v.source, blocked=v.blocked)
    return v


model_armor._call = timed_call

_orig_chat = main._screened_chat


async def screened(store, req, request):
    current["turn"] = next(turn_ids)
    t0 = time.perf_counter()
    try:
        return await _orig_chat(store, req, request)
    finally:
        emit(kind="turn", dt=round(time.perf_counter() - t0, 4))


main._screened_chat = screened

if __name__ == "__main__":
    uvicorn.run(main.app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
