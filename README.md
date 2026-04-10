# promptci

**Prompt versioning with CI/CD regression gates — for production LLM engineering.**

Version, diff, test, and deploy prompts with quality gates, schema migration, PII scrubbing, and full observability.

```bash
pip install promptci
```

---

## Why promptci?

In 2026, prompt changes are the most common cause of silent LLM regressions. Teams edit prompts in Google Docs, paste them into code, and ship — with zero version control, no diff visibility, and no quality gates. When output quality degrades, nobody knows which prompt change caused it.

`promptci` brings software engineering discipline to prompt management.

---

## Quickstart

```python
from promptci import (
    PromptRegistry, PromptVersion, PromptStatus,
    LengthGate, VariableGate, InjectionRiskGate, RegressionGatePipeline,
)

# Create and register a versioned prompt
registry = PromptRegistry()

prompt_v1 = PromptVersion(
    name="summarize",
    version="1.0.0",
    content="Summarize the following text: {{text}}. Be concise.",
    tags=["summarization"],
    status=PromptStatus.ACTIVE,
)
registry.register(prompt_v1)

# Render with variable substitution
rendered = registry.render("summarize", {"text": "The quick brown fox..."})
print(rendered)

# Run CI gates before deploying v2
pipeline = (
    RegressionGatePipeline()
    .add_gate(LengthGate(min_chars=20, max_chars=5000))
    .add_gate(VariableGate(required=["text"]))
    .add_gate(InjectionRiskGate())
)
report = pipeline.run(prompt_v1)
print(f"Gates passed: {report.overall_passed}")
```

---

## Built-in Regression Gates

| Gate | Description |
|------|-------------|
| `LengthGate` | Min/max character length check |
| `VariableGate` | Required `{{variable}}` presence |
| `InjectionRiskGate` | Blocks injection patterns (ignore previous instructions, etc.) |
| `KeywordCoverageGate` | Required keywords coverage fraction |

---

## Prompt Diff

```python
from promptci import diff_prompts, diff_to_unified

diff = diff_prompts(prompt_v1, prompt_v2)
print(diff.summary())        # ScoreDiff summary
print(diff.changed)          # True / False
print(diff.char_delta)       # Character delta

print(diff_to_unified(prompt_v1, prompt_v2))   # Unified diff string
```

---

## Advanced Features

### Caching (LRU + TTL + SHA-256)

```python
from promptci.advanced import PromptCache

cache = PromptCache(max_size=1000, ttl=600)
memoized_render = cache.memoize(registry.render)
rendered = memoized_render("summarize", "1.0.0", {"text": "hello"})
print(cache.stats())
```

### Prompt Pipeline

```python
from promptci.advanced import PromptPipeline

pipeline = (
    PromptPipeline()
    .map("strip_trailing", lambda p: p.model_copy(update={"content": p.content.strip()}))
    .filter("active_only", lambda p: p.status == PromptStatus.ACTIVE)
    .with_retry("strip_trailing", retries=2)
)
result = pipeline.run(prompt_v1)
print(pipeline.audit_log)
```

### Declarative Validation + Schema Evolution

```python
from promptci.advanced import PromptValidator, PromptRule, SchemaEvolver

validator = (
    PromptValidator()
    .add_rule(PromptRule("non_empty", lambda p: len(p.content) > 0, "Content required"))
    .add_rule(PromptRule("has_tags", lambda p: len(p.tags) > 0, "At least one tag required"))
)
violations = validator.validate(prompt_v1)

evolver = SchemaEvolver()
evolver.register_migration("1.0.0", "2.0.0", lambda p: p.model_copy(update={"description": "v2 prompt"}))
prompt_v2 = evolver.migrate(prompt_v1, "2.0.0")
```

### PII Scrubbing

```python
from promptci.advanced import PIIScrubber

scrubber = PIIScrubber()
clean = scrubber.scrub("Contact: john@example.com, SSN: 123-45-6789")
# → "Contact: [EMAIL], SSN: [SSN]"
```

### Async Batch Registration

```python
from promptci.advanced import abatch_register, batch_register
import asyncio

asyncio.run(abatch_register(prompt_list, registry.register))
batch_register(prompt_list, registry.register, max_workers=8)
```

### Rate Limiter (sync + async)

```python
from promptci.advanced import RateLimiter

limiter = RateLimiter(rate=50, capacity=50)
if limiter.acquire():
    rendered = registry.render("summarize", {"text": "..."})
```

### Observability

```python
from promptci.advanced import PromptProfiler, DriftDetector, CIReportExporter

profiler = PromptProfiler()
profiled_render = profiler.profile(registry.render)
profiled_render("summarize", {"text": "hi"})
print(profiler.report())

detector = DriftDetector(threshold=0.05)
detector.set_baseline(report_v1)
drifts = detector.detect(report_v2)

exporter = CIReportExporter(report)
print(exporter.to_json())
print(exporter.to_csv())
print(exporter.to_markdown())
```

### Streaming

```python
from promptci.advanced import stream_versions, versions_to_ndjson

for pv in stream_versions(prompt_list):
    print(pv.name, pv.version)

for line in versions_to_ndjson(prompt_list):
    print(line)
```

### Regression Tracking

```python
from promptci.advanced import PromptRegressionTracker, ScoreTrend

tracker = PromptRegressionTracker(window=20)
tracker.record(report_v1)
tracker.record(report_v2)
print(tracker.trend())               # "improving" / "declining" / "stable"
print(tracker.latest_regression())

trend = ScoreTrend(window=10)
for score in [0.7, 0.8, 0.9]:
    trend.record(score)
print(trend.trend(), trend.volatility())
```

### Audit Log + Cost Ledger + Model Router

```python
from promptci.advanced import AuditLog, CostLedger, ModelRouter

log = AuditLog()
log.log("deploy", {"name": "summarize", "version": "2.0.0"})

ledger = CostLedger()
ledger.record("summarize", "2.0.0", tokens=500, cost_usd=0.01)
print(ledger.summary())

router = ModelRouter(cheap_threshold=200)
model = router.route(prompt_v1)   # "gpt-4o-mini" or "gpt-4o"
```

---

## Persistence

```python
registry.save("registry.json")
registry.load("registry.json")
```

---

## Installation

```bash
pip install promptci
```

Python 3.8+ · No external dependencies (stdlib + pydantic)

---

## Changelog

### v1.1.3 (2026-04-10)
- Added Changelog section to README for release traceability
- SEO improvements: prompt versioning, CI/CD regression gate, LLM prompt management

### v1.1.0
- Renamed module to `promptci` to match PyPI package name
- Added schema migration, PII scrubbing, quality gates, full observability

### v1.0.0
- Initial release: prompt versioning, diff, test, deploy

## License

MIT

## Contributing

Contributions are welcome! Here's how to get started:

1. Fork the repository on [GitHub](https://github.com/maheshmakvana/promptci)
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes and add tests
4. Run the test suite: `pytest tests/ -v`
5. Submit a pull request

Please open an issue first for major changes to discuss the approach.

## Author

**Mahesh Makvana** — [GitHub](https://github.com/maheshmakvana) · [PyPI](https://pypi.org/user/maheshmakvana/)

MIT License
