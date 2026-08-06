"""Structured observability: tracer + decorators (Member C, D4)."""
import time, functools
from typing import List
from datetime import datetime, timezone

# ============================================================
# SECTION 2 — OBSERVABILITY LAYER   [Member C]  (D4: monitoring)
# ============================================================
# Structured tracing — NOT print statements. Every node and tool is wrapped
# by @traced, which records name, kind, latency, success/failure, and timestamp
# into a central Tracer. LLM token usage (=> cost) is recorded separately.
# A metrics dashboard is rendered at the end of the run (Section 11).

class Tracer:
    def __init__(self):
        self.spans: List[dict] = []
        self.llm_usage: List[dict] = []

    def record(self, span: dict):
        self.spans.append(span)

    def record_llm(self, label: str, usage: dict):
        self.llm_usage.append({"label": label, **usage})

    def summary(self) -> dict:
        agg = {}
        for s in self.spans:
            a = agg.setdefault(s["name"], {"kind": s["kind"], "calls": 0, "total_ms": 0.0, "failures": 0})
            a["calls"] += 1
            a["total_ms"] = round(a["total_ms"] + s["latency_ms"], 2)
            a["failures"] += 0 if s["ok"] else 1
        return agg

    def tokens_and_cost(self, in_rate=0.59/1e6, out_rate=0.79/1e6):
        # Rates are illustrative (Groq per-token, update if pricing changes).
        ti = sum(u.get("input_tokens", 0) for u in self.llm_usage)
        to = sum(u.get("output_tokens", 0) for u in self.llm_usage)
        return ti, to, round(ti * in_rate + to * out_rate, 6)

TRACER = Tracer()

def traced(kind: str):
    """Decorator: wrap a node ('node') or tool ('tool') so every call is traced."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.perf_counter(); ok = True; err = None
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                ok = False; err = repr(e); raise
            finally:
                TRACER.record({
                    "name": fn.__name__, "kind": kind,
                    "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                    "ok": ok, "error": err,
                    "ts": datetime.now(timezone.utc).isoformat(),
                })
        return wrapper
    return deco

def record_llm_usage(response, label: str):
    """Pull token usage off a LangChain response (Groq populates usage_metadata)."""
    usage = getattr(response, "usage_metadata", None) or {}
    TRACER.record_llm(label, {
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
    })
