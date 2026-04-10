"""
Advanced features for promptci — 2026 Standard.

Covers: Caching, Pipeline, Validation & Schema, Async & Concurrency,
Observability, Streaming & Storage, Diff & Regression, Security & Cost.
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

from promptci.exceptions import RegressionGateError, ValidationError
from promptci.models import CIReport, GateResult, PromptDiffResult, PromptVersion

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 1. CACHING
# ─────────────────────────────────────────────

class PromptCache:
    """LRU + TTL cache for rendered prompts, keyed by SHA-256."""

    def __init__(self, max_size: int = 512, ttl: float = 300.0) -> None:
        self.max_size = max_size
        self.ttl = ttl
        self._store: Dict[str, Tuple[str, float]] = {}
        self._order: deque = deque()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _key(prompt_name: str, version: str, variables: Dict[str, str]) -> str:
        raw = json.dumps({"n": prompt_name, "v": version, "vars": variables}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, prompt_name: str, version: str, variables: Dict[str, str]) -> Optional[str]:
        """Return cached rendered text or None."""
        k = self._key(prompt_name, version, variables)
        with self._lock:
            if k in self._store:
                val, ts = self._store[k]
                if time.time() - ts <= self.ttl:
                    self._hits += 1
                    return val
                del self._store[k]
            self._misses += 1
        return None

    def put(self, prompt_name: str, version: str, variables: Dict[str, str], rendered: str) -> None:
        """Cache a rendered prompt."""
        k = self._key(prompt_name, version, variables)
        with self._lock:
            if k in self._store:
                self._order.remove(k)
            elif len(self._store) >= self.max_size:
                oldest = self._order.popleft()
                self._store.pop(oldest, None)
            self._store[k] = (rendered, time.time())
            self._order.append(k)

    def memoize(self, render_fn: Callable[..., str]) -> Callable[..., str]:
        """Decorator: cache results of a render function."""
        def wrapper(prompt_name: str, version: str, variables: Dict[str, str]) -> str:
            cached = self.get(prompt_name, version, variables)
            if cached is not None:
                return cached
            result = render_fn(prompt_name, version, variables)
            self.put(prompt_name, version, variables, result)
            return result
        return wrapper

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._store),
                "max_size": self.max_size,
                "ttl": self.ttl,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / total if total > 0 else 0.0,
            }

    def save(self, path: str) -> None:
        with self._lock:
            data = {k: list(v) for k, v in self._store.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        logger.info("PromptCache saved to %s", path)

    def load(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        with self._lock:
            for k, (val, ts) in data.items():
                self._store[k] = (val, ts)
                self._order.append(k)
        logger.info("PromptCache loaded from %s", path)


# ─────────────────────────────────────────────
# 2. PIPELINE
# ─────────────────────────────────────────────

@dataclass
class _PromptPipelineStep:
    name: str
    fn: Callable[[PromptVersion], PromptVersion]
    retries: int = 0


class PromptPipeline:
    """Fluent, auditable prompt transformation pipeline."""

    def __init__(self) -> None:
        self._steps: List[_PromptPipelineStep] = []
        self._audit_log: List[Dict[str, Any]] = []

    def map(self, name: str, fn: Callable[[PromptVersion], PromptVersion]) -> "PromptPipeline":
        """Apply a transformation to each prompt."""
        self._steps.append(_PromptPipelineStep(name, fn))
        return self

    def filter(self, name: str, pred: Callable[[PromptVersion], bool]) -> "PromptPipeline":
        """Keep prompts matching predicate (returns same prompt or raises to skip)."""
        def _filter_fn(pv: PromptVersion) -> PromptVersion:
            if not pred(pv):
                raise _SkipStep()
            return pv
        self._steps.append(_PromptPipelineStep(name, _filter_fn))
        return self

    def with_retry(self, step_name: str, retries: int = 2) -> "PromptPipeline":
        for step in self._steps:
            if step.name == step_name:
                step.retries = retries
        return self

    def run(self, prompt: PromptVersion) -> Optional[PromptVersion]:
        """Run all pipeline steps on a single prompt."""
        result = prompt
        for step in self._steps:
            start = time.time()
            attempt = 0
            last_exc: Optional[Exception] = None
            while attempt <= step.retries:
                try:
                    result = step.fn(result)
                    break
                except _SkipStep:
                    self._audit_log.append({"step": step.name, "action": "skipped"})
                    return None
                except Exception as exc:
                    last_exc = exc
                    attempt += 1
            else:
                raise ValidationError(f"Step '{step.name}' failed after {step.retries + 1} attempts") from last_exc
            elapsed = time.time() - start
            self._audit_log.append({"step": step.name, "elapsed_s": elapsed, "version": result.version})
        return result

    async def arun(self, prompt: PromptVersion) -> Optional[PromptVersion]:
        """Async pipeline execution."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.run, prompt)

    @property
    def audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)


class _SkipStep(Exception):
    pass


# ─────────────────────────────────────────────
# 3. VALIDATION & SCHEMA
# ─────────────────────────────────────────────

@dataclass
class PromptRule:
    """Declarative validation rule for a PromptVersion."""
    name: str
    check: Callable[[PromptVersion], bool]
    message: str


class PromptValidator:
    """Declarative prompt validator with rule registration."""

    def __init__(self) -> None:
        self._rules: List[PromptRule] = []

    def add_rule(self, rule: PromptRule) -> "PromptValidator":
        self._rules.append(rule)
        return self

    def validate(self, prompt: PromptVersion) -> List[str]:
        violations = []
        for rule in self._rules:
            try:
                if not rule.check(prompt):
                    violations.append(rule.message)
            except Exception as exc:
                violations.append(f"Rule '{rule.name}' error: {exc}")
        return violations

    def is_valid(self, prompt: PromptVersion) -> bool:
        return len(self.validate(prompt)) == 0


class SchemaEvolver:
    """Version-to-version prompt migration registry."""

    def __init__(self) -> None:
        # (from_version, to_version) → migration fn
        self._migrations: Dict[Tuple[str, str], Callable[[PromptVersion], PromptVersion]] = {}

    def register_migration(
        self,
        from_version: str,
        to_version: str,
        fn: Callable[[PromptVersion], PromptVersion],
    ) -> None:
        self._migrations[(from_version, to_version)] = fn
        logger.info("Migration registered: %s → %s", from_version, to_version)

    def migrate(self, prompt: PromptVersion, to_version: str) -> PromptVersion:
        """Apply a registered migration."""
        key = (prompt.version, to_version)
        if key not in self._migrations:
            raise ValidationError(f"No migration from v{prompt.version} to v{to_version}")
        result = self._migrations[key](prompt)
        return result.model_copy(update={"version": to_version})


class ConfidenceScorer:
    """Heuristic 0–1 quality confidence for a PromptVersion."""

    def score(self, prompt: PromptVersion) -> float:
        """Combine length, variable coverage, and tag richness."""
        length_score = min(1.0, len(prompt.content) / 500)
        var_score = min(1.0, len(prompt.variables) / 5) if prompt.variables else 0.5
        tag_score = min(1.0, len(prompt.tags) / 3) if prompt.tags else 0.3
        return round((length_score + var_score + tag_score) / 3, 4)


class PIIScrubber:
    """Detect and mask PII patterns in prompt content."""

    import re as _re_module
    _PATTERNS = [
        (_re_module.compile(r'\b\d{3}-\d{2}-\d{4}\b'), "[SSN]"),           # SSN
        (_re_module.compile(r'\b\d{16}\b'), "[CARD]"),                       # Credit card
        (_re_module.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'), "[EMAIL]"),
        (_re_module.compile(r'\b\d{3}[\-.\s]?\d{3}[\-.\s]?\d{4}\b'), "[PHONE]"),
    ]

    def scrub(self, text: str) -> str:
        """Return text with PII replaced by placeholder tags."""
        for pattern, replacement in self._PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def has_pii(self, text: str) -> bool:
        return any(p.search(text) for p, _ in self._PATTERNS)


# ─────────────────────────────────────────────
# 4. ASYNC & CONCURRENCY
# ─────────────────────────────────────────────

class RateLimiter:
    """Token-bucket rate limiter (sync + async)."""

    def __init__(self, rate: float, capacity: float) -> None:
        self.rate = rate
        self.capacity = capacity
        self._tokens = capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last = now

    def acquire(self, tokens: float = 1.0) -> bool:
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
        return False

    async def aacquire(self, tokens: float = 1.0) -> bool:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.acquire, tokens)


async def abatch_register(
    prompts: List[PromptVersion],
    register_fn: Callable[[PromptVersion], None],
    concurrency: int = 8,
) -> None:
    """Async batch registration of prompt versions."""
    sem = asyncio.Semaphore(concurrency)

    async def _register(pv: PromptVersion) -> None:
        async with sem:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, register_fn, pv)

    await asyncio.gather(*[_register(pv) for pv in prompts])


def batch_register(
    prompts: List[PromptVersion],
    register_fn: Callable[[PromptVersion], None],
    max_workers: int = 4,
) -> None:
    """Sync concurrent batch registration."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(register_fn, prompts))


class CancellationToken:
    """Cooperative cancellation token for async operations."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


# ─────────────────────────────────────────────
# 5. OBSERVABILITY
# ─────────────────────────────────────────────

class PromptProfiler:
    """Track render timing and metadata per prompt call."""

    def __init__(self) -> None:
        self._records: List[Dict[str, Any]] = []

    def profile(self, render_fn: Callable[..., str]) -> Callable[..., str]:
        """Wrap a render function with timing."""
        def wrapper(*args: Any, **kwargs: Any) -> str:
            start = time.perf_counter()
            result = render_fn(*args, **kwargs)
            elapsed = time.perf_counter() - start
            self._records.append({
                "args": str(args[:2]),
                "elapsed_s": round(elapsed, 6),
                "output_len": len(result),
            })
            return result
        return wrapper

    def report(self) -> Dict[str, Any]:
        if not self._records:
            return {"calls": 0}
        elapsed_vals = [r["elapsed_s"] for r in self._records]
        return {
            "calls": len(self._records),
            "mean_elapsed_s": sum(elapsed_vals) / len(elapsed_vals),
            "max_elapsed_s": max(elapsed_vals),
            "records": self._records,
        }


class DriftDetector:
    """Detect prompt score drift across CI runs."""

    def __init__(self, threshold: float = 0.05) -> None:
        self.threshold = threshold
        self._baseline: Optional[Dict[str, float]] = None

    def set_baseline(self, report: CIReport) -> None:
        self._baseline = {g.gate_name: g.score for g in report.gates}

    def detect(self, report: CIReport) -> Dict[str, float]:
        if not self._baseline:
            return {}
        drifts: Dict[str, float] = {}
        for gate in report.gates:
            base = self._baseline.get(gate.gate_name, gate.score)
            drift = abs(gate.score - base)
            if drift >= self.threshold:
                drifts[gate.gate_name] = round(drift, 4)
        return drifts


class CIReportExporter:
    """Export CIReport to JSON, CSV, or Markdown."""

    def __init__(self, report: CIReport) -> None:
        self._report = report

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self._report.model_dump(), indent=indent, default=str)

    def to_csv(self) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["gate", "passed", "score", "threshold", "message"])
        for g in self._report.gates:
            writer.writerow([g.gate_name, g.passed, g.score, g.threshold, g.message])
        return buf.getvalue()

    def to_markdown(self) -> str:
        r = self._report
        lines = [
            f"# CI Report: {r.prompt_name} v{r.version}",
            f"**Overall:** {'PASS' if r.overall_passed else 'FAIL'}",
            "",
            "| Gate | Score | Threshold | Passed | Message |",
            "|------|-------|-----------|--------|---------|",
        ]
        for g in r.gates:
            lines.append(f"| {g.gate_name} | {g.score:.2f} | {g.threshold:.2f} | {g.passed} | {g.message} |")
        return "\n".join(lines)


# ─────────────────────────────────────────────
# 6. STREAMING & STORAGE
# ─────────────────────────────────────────────

def stream_versions(
    prompts: List[PromptVersion],
) -> Generator[PromptVersion, None, None]:
    """Stream PromptVersion objects one at a time."""
    for pv in prompts:
        yield pv


def versions_to_ndjson(prompts: List[PromptVersion]) -> Generator[str, None, None]:
    """Stream NDJSON lines for prompt versions."""
    for pv in prompts:
        yield json.dumps(pv.model_dump(), default=str)


# ─────────────────────────────────────────────
# 7. DIFF & REGRESSION
# ─────────────────────────────────────────────

class PromptRegressionTracker:
    """Track CI report history and detect regressions."""

    def __init__(self, window: int = 20) -> None:
        self.window = window
        self._history: deque = deque(maxlen=window)

    def record(self, report: CIReport) -> None:
        self._history.append(report)

    def trend(self) -> str:
        if len(self._history) < 2:
            return "stable"
        pass_rates = [
            sum(1 for g in r.gates if g.passed) / max(len(r.gates), 1)
            for r in self._history
        ]
        deltas = [pass_rates[i + 1] - pass_rates[i] for i in range(len(pass_rates) - 1)]
        mean_delta = sum(deltas) / len(deltas)
        if mean_delta > 0.01:
            return "improving"
        if mean_delta < -0.01:
            return "declining"
        return "stable"

    def latest_regression(self) -> Optional[Dict[str, Any]]:
        if len(self._history) < 2:
            return None
        a, b = list(self._history)[-2], list(self._history)[-1]
        regressed_gates = [
            g.gate_name for g in b.gates
            if not g.passed and any(ag.gate_name == g.gate_name and ag.passed for ag in a.gates)
        ]
        return {
            "from_timestamp": a.timestamp,
            "to_timestamp": b.timestamp,
            "regressed_gates": regressed_gates,
            "has_regression": bool(regressed_gates),
        }


class ScoreTrend:
    """Rolling score trend with volatility tracking."""

    def __init__(self, window: int = 10) -> None:
        self.window = window
        self._scores: deque = deque(maxlen=window)

    def record(self, score: float) -> None:
        self._scores.append(score)

    def trend(self) -> str:
        if len(self._scores) < 2:
            return "stable"
        scores = list(self._scores)
        delta = scores[-1] - scores[0]
        if delta > 0.05:
            return "improving"
        if delta < -0.05:
            return "declining"
        return "stable"

    def volatility(self) -> float:
        if len(self._scores) < 2:
            return 0.0
        scores = list(self._scores)
        mean = sum(scores) / len(scores)
        return (sum((s - mean) ** 2 for s in scores) / len(scores)) ** 0.5


# ─────────────────────────────────────────────
# 8. SECURITY & COST
# ─────────────────────────────────────────────

class AuditLog:
    """Append-only audit log for prompt registry operations."""

    def __init__(self) -> None:
        self._entries: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def log(self, event: str, data: Dict[str, Any]) -> None:
        entry = {"event": event, "timestamp": time.time(), **data}
        with self._lock:
            self._entries.append(entry)

    def to_json(self, indent: int = 2) -> str:
        with self._lock:
            return json.dumps(self._entries, indent=indent, default=str)

    @property
    def entries(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._entries)


@dataclass
class CostLedger:
    """Track render/API costs for prompt operations."""
    _entries: List[Dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, prompt_name: str, version: str, tokens: int, cost_usd: float) -> None:
        with self._lock:
            self._entries.append({
                "prompt_name": prompt_name,
                "version": version,
                "tokens": tokens,
                "cost_usd": cost_usd,
                "timestamp": time.time(),
            })

    def total_cost(self) -> float:
        with self._lock:
            return sum(e["cost_usd"] for e in self._entries)

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "calls": len(self._entries),
                "total_tokens": sum(e["tokens"] for e in self._entries),
                "total_cost_usd": self.total_cost(),
            }


class ModelRouter:
    """Route prompt render/eval to cheap vs. frontier model based on complexity."""

    def __init__(self, cheap_threshold: int = 200, frontier_model: str = "gpt-4o", cheap_model: str = "gpt-4o-mini") -> None:
        self.cheap_threshold = cheap_threshold
        self.frontier_model = frontier_model
        self.cheap_model = cheap_model

    def route(self, prompt: PromptVersion) -> str:
        """Return recommended model name based on prompt length."""
        if len(prompt.content) <= self.cheap_threshold:
            return self.cheap_model
        return self.frontier_model
