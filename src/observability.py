"""Dependency-free tracing/metrics with optional OpenTelemetry export.

Every pipeline stage is a span; per-request token and cost estimates are
recorded; aggregates are exposed as JSON and Prometheus text. If the
`opentelemetry` SDK is installed and OTEL_EXPORTER_OTLP_ENDPOINT is set, spans
are also emitted through it."""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from threading import Lock

# USD per 1M tokens (input, output). Estimates for dashboards, not billing.
PRICES = {"gemini-3.1-flash-lite": (0.10, 0.40), "claude-opus-5": (15.0, 75.0),
          "claude-sonnet-5": (3.0, 15.0), "local": (0.0, 0.0)}


def estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def estimate_cost(model: str | None, tokens_in: int, tokens_out: int) -> float:
    name = (model or "local").split(":", 1)[-1]
    if (model or "").startswith("local"):
        name = "local"
    pin, pout = PRICES.get(name, (0.0, 0.0))
    return (tokens_in * pin + tokens_out * pout) / 1_000_000


try:  # optional
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry import trace as _otel
        _tracer = _otel.get_tracer("finsight")
    else:
        _tracer = None
except Exception:  # pragma: no cover
    _tracer = None


class Metrics:
    def __init__(self, window: int = 500):
        self.lock = Lock()
        self.stage_ms: dict[str, deque] = defaultdict(lambda: deque(maxlen=window))
        self.counters: dict[str, float] = defaultdict(float)
        self.by_route: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    def observe(self, stage: str, ms: float):
        with self.lock:
            self.stage_ms[stage].append(ms)

    def inc(self, name: str, value: float = 1.0):
        with self.lock:
            self.counters[name] += value

    def record_request(self, *, route: str, model: str | None, tokens_in: int, tokens_out: int,
                       correct: bool | None = None, flags=()):
        cost = estimate_cost(model, tokens_in, tokens_out)
        with self.lock:
            r = self.by_route[route]
            r["requests"] += 1
            r["tokens_in"] += tokens_in
            r["tokens_out"] += tokens_out
            r["cost_usd"] += cost
            if correct is not None:
                r["judged"] += 1
                r["correct"] += bool(correct)
            for f in flags:
                self.counters[f"flag:{str(f).split(':')[0]}"] += 1
            self.counters["requests"] += 1

    @staticmethod
    def _pct(values, q):
        if not values:
            return 0.0
        s = sorted(values)
        return round(s[min(len(s) - 1, int(q * len(s)))], 2)

    def summary(self) -> dict:
        with self.lock:
            stages = {k: {"count": len(v), "p50_ms": self._pct(v, .5), "p95_ms": self._pct(v, .95)}
                      for k, v in self.stage_ms.items()}
            routes = {}
            for name, r in self.by_route.items():
                row = dict(r)
                row["cost_per_request_usd"] = round(r["cost_usd"] / r["requests"], 6) if r["requests"] else 0.0
                row["cost_per_correct_answer_usd"] = (round(r["cost_usd"] / r["correct"], 6)
                                                      if r.get("correct") else None)
                routes[name] = row
            return {"stages": stages, "routes": routes, "counters": dict(self.counters)}

    def prometheus(self) -> str:
        s, lines = self.summary(), []
        for stage, v in s["stages"].items():
            lines.append(f'finsight_stage_latency_ms{{stage="{stage}",quantile="0.95"}} {v["p95_ms"]}')
            lines.append(f'finsight_stage_latency_ms{{stage="{stage}",quantile="0.5"}} {v["p50_ms"]}')
        for route, r in s["routes"].items():
            lines.append(f'finsight_cost_usd_total{{route="{route}"}} {r["cost_usd"]}')
            lines.append(f'finsight_requests_total{{route="{route}"}} {r["requests"]}')
        for name, v in s["counters"].items():
            safe = "".join(c if c.isalnum() else "_" for c in name)
            lines.append(f"finsight_{safe} {v}")
        return "\n".join(lines) + "\n"


METRICS = Metrics()


@contextmanager
def span(stage: str, **attrs):
    """Time a stage into METRICS (and OpenTelemetry when configured)."""
    start = time.perf_counter()
    ctx = _tracer.start_as_current_span(stage) if _tracer else None
    try:
        if ctx:
            s = ctx.__enter__()
            for k, v in attrs.items():
                s.set_attribute(k, str(v))
        yield
    finally:
        METRICS.observe(stage, (time.perf_counter() - start) * 1000)
        if ctx:
            ctx.__exit__(None, None, None)
