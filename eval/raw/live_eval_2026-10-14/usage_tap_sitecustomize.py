"""Usage tap for the Task 2 evals (scratch tooling, imported by the interpreter via PYTHONPATH).

When TAAL_TAP_LOG is set it
  * wraps agents.vertex_models._AdaptedGemini.generate_content_async: one JSONL line per model call
    (requested model, model_version the server reports, usage_metadata counts, error status), and a
    hard spend guard: before each call, if cumulative spend (TAAL_TAP_PRIOR_USD + this process) would
    exceed TAAL_TAP_CAP_USD the process exits with code 42 without sending the call;
  * lowers adk eval's inference/evaluate parallelism (default 4) to TAAL_TAP_PARALLELISM (default 2).
Prices are config/models.toml [pricing] for gemini-3.5-flash; other models are costed at the same
rates and flagged (a fallback call marks the run INVALID anyway).
"""
import importlib.abc
import importlib.util
import json
import os
import sys
import time

LOG = os.environ.get("TAAL_TAP_LOG")
if LOG:
    CAP = float(os.environ.get("TAAL_TAP_CAP_USD", "0") or 0)
    PRIOR = float(os.environ.get("TAAL_TAP_PRIOR_USD", "0") or 0)
    PAR = int(os.environ.get("TAAL_TAP_PARALLELISM", "2"))
    P_IN, P_OUT, DISC = 1.65e-6, 9.90e-6, 0.9
    state = {"usd": 0.0, "inflight": 0, "max_inflight": 0, "calls": 0}
    GUARD_MARGIN = 0.15  # a single planner call is about $0.02; stop before the cap, never after

    def _write(rec):
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _cost(u):
        prompt = u.get("prompt", 0)
        cached = u.get("cached", 0)
        return (prompt - cached) * P_IN + cached * P_IN * (1 - DISC) + (u.get("candidates", 0) + u.get("thoughts", 0)) * P_OUT

    def _patch_models(mod):
        cls = mod._AdaptedGemini
        orig = cls.generate_content_async

        async def wrapped(self, llm_request, stream=False):
            if CAP and PRIOR + state["usd"] + GUARD_MARGIN >= CAP:
                _write({"event": "cap_stop", "prior_usd": PRIOR, "run_usd": round(state["usd"], 6), "cap_usd": CAP, "t": time.time()})
                sys.stderr.write("usage tap: spend cap reached, exiting\n")
                sys.stderr.flush()
                os._exit(42)
            state["inflight"] += 1
            state["max_inflight"] = max(state["max_inflight"], state["inflight"])
            t0 = time.time()
            last = None
            version = None
            err = None
            try:
                async for resp in orig(self, llm_request, stream):
                    um = getattr(resp, "usage_metadata", None)
                    if um is not None:
                        last = um
                    version = getattr(resp, "model_version", None) or version
                    yield resp
            except BaseException as e:  # noqa: BLE001
                code = None
                try:
                    from agents.vertex_models import status_of
                    code = status_of(e)
                except Exception:
                    pass
                err = {"type": type(e).__name__, "status": code, "msg": str(e)[:160]}
                raise
            finally:
                state["inflight"] -= 1
                u = {}
                if last is not None:
                    u = {"prompt": int(last.prompt_token_count or 0), "candidates": int(last.candidates_token_count or 0),
                         "thoughts": int(last.thoughts_token_count or 0), "cached": int(last.cached_content_token_count or 0)}
                usd = _cost(u) if u else 0.0
                state["usd"] += usd
                state["calls"] += 1
                _write({"event": "call", "requested_model": self.model, "model_version": version, "usage": u, "usd": round(usd, 6),
                        "error": err, "elapsed_s": round(time.time() - t0, 2), "inflight_max": state["max_inflight"], "t": round(t0, 2), "pid": os.getpid()})

        cls.generate_content_async = wrapped

    def _patch_parallelism(mod):
        for name in ("InferenceConfig", "EvaluateConfig"):
            c = getattr(mod, name)
            c.model_fields["parallelism"].default = PAR
            c.model_rebuild(force=True)
        _write({"event": "parallelism_set", "value": PAR, "pid": os.getpid()})

    HOOKS = {"agents.vertex_models": _patch_models, "google.adk.evaluation.base_eval_service": _patch_parallelism}

    class _Finder(importlib.abc.MetaPathFinder):
        busy = set()

        def find_spec(self, name, path, target=None):
            if name not in HOOKS or name in self.busy:
                return None
            self.busy.add(name)
            try:
                spec = importlib.util.find_spec(name)
            finally:
                self.busy.discard(name)
            if spec is None or spec.loader is None:
                return None
            loader = spec.loader
            orig_exec = loader.exec_module

            def exec_module(module, _o=orig_exec, _n=name):
                _o(module)
                HOOKS[_n](module)

            loader.exec_module = exec_module
            return spec

    sys.meta_path.insert(0, _Finder())
