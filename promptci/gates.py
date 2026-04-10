"""Regression gates — CI/CD quality checks for prompt versions."""
from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from typing import List

from promptci.exceptions import RegressionGateError
from promptci.models import CIReport, GateResult, PromptVersion

logger = logging.getLogger(__name__)


class BaseGate(ABC):
    """Abstract regression gate."""

    name: str = "base"

    @abstractmethod
    def check(self, prompt: PromptVersion) -> GateResult:
        """Run the gate and return a GateResult."""


class LengthGate(BaseGate):
    """Gate: prompt must be between min_chars and max_chars."""

    name = "length"

    def __init__(self, min_chars: int = 20, max_chars: int = 8000, threshold: float = 1.0) -> None:
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.threshold = threshold

    def check(self, prompt: PromptVersion) -> GateResult:
        n = len(prompt.content)
        passed = self.min_chars <= n <= self.max_chars
        score = 1.0 if passed else 0.0
        return GateResult(
            prompt_name=prompt.name,
            version=prompt.version,
            gate_name=self.name,
            passed=passed,
            score=score,
            threshold=self.threshold,
            message=f"Length {n} chars; required [{self.min_chars}, {self.max_chars}]",
        )


class VariableGate(BaseGate):
    """Gate: prompt must contain all required variables."""

    name = "variables"

    def __init__(self, required: List[str], threshold: float = 1.0) -> None:
        self.required = required
        self.threshold = threshold

    def check(self, prompt: PromptVersion) -> GateResult:
        missing = [v for v in self.required if v not in prompt.variables]
        score = 1.0 - len(missing) / max(len(self.required), 1)
        passed = score >= self.threshold
        return GateResult(
            prompt_name=prompt.name,
            version=prompt.version,
            gate_name=self.name,
            passed=passed,
            score=score,
            threshold=self.threshold,
            message=f"Missing variables: {missing}" if missing else "All required variables present",
        )


class InjectionRiskGate(BaseGate):
    """Gate: prompt must not contain injection risk patterns."""

    name = "injection_risk"

    _PATTERNS = [
        re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
        re.compile(r"you\s+are\s+now\s+", re.I),
        re.compile(r"disregard\s+(your\s+)?", re.I),
        re.compile(r"system\s*:\s*", re.I),
        re.compile(r"<\s*script\s*>", re.I),
    ]

    def __init__(self, threshold: float = 1.0) -> None:
        self.threshold = threshold

    def check(self, prompt: PromptVersion) -> GateResult:
        hits = [p.pattern for p in self._PATTERNS if p.search(prompt.content)]
        score = 1.0 if not hits else 0.0
        passed = score >= self.threshold
        return GateResult(
            prompt_name=prompt.name,
            version=prompt.version,
            gate_name=self.name,
            passed=passed,
            score=score,
            threshold=self.threshold,
            message=f"Injection risk patterns found: {hits}" if hits else "No injection risk detected",
        )


class KeywordCoverageGate(BaseGate):
    """Gate: prompt must contain at least `coverage` fraction of required keywords."""

    name = "keyword_coverage"

    def __init__(self, keywords: List[str], coverage: float = 0.8, threshold: float = 0.8) -> None:
        self.keywords = keywords
        self.coverage = coverage
        self.threshold = threshold

    def check(self, prompt: PromptVersion) -> GateResult:
        content_lower = prompt.content.lower()
        found = [kw for kw in self.keywords if kw.lower() in content_lower]
        score = len(found) / max(len(self.keywords), 1)
        passed = score >= self.threshold
        return GateResult(
            prompt_name=prompt.name,
            version=prompt.version,
            gate_name=self.name,
            passed=passed,
            score=score,
            threshold=self.threshold,
            message=f"Coverage {score:.1%}: found {found}",
        )


class RegressionGatePipeline:
    """Run a sequence of gates and produce a CIReport."""

    def __init__(self) -> None:
        self._gates: List[BaseGate] = []

    def add_gate(self, gate: BaseGate) -> "RegressionGatePipeline":
        """Register a gate."""
        self._gates.append(gate)
        return self

    def run(self, prompt: PromptVersion, fail_fast: bool = False) -> CIReport:
        """Execute all gates and return a CIReport."""
        results: List[GateResult] = []
        for gate in self._gates:
            result = gate.check(prompt)
            results.append(result)
            logger.info(
                "Gate '%s' on '%s' v%s: %s (score=%.2f)",
                gate.name, prompt.name, prompt.version,
                "PASS" if result.passed else "FAIL", result.score,
            )
            if fail_fast and not result.passed:
                raise RegressionGateError(
                    f"Gate '{gate.name}' failed for '{prompt.name}' v{prompt.version}: {result.message}"
                )
        overall = all(r.passed for r in results)
        return CIReport(
            prompt_name=prompt.name,
            version=prompt.version,
            gates=results,
            overall_passed=overall,
        )
