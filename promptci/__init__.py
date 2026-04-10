"""
promptci — Prompt Versioning with CI/CD & Regression Gates.

Manage, version, test, and deploy prompts with structured quality gates,
diff tracking, schema evolution, and production observability.
"""
from promptci.models import (
    PromptStatus,
    PromptVersion,
    PromptDiffResult,
    GateResult,
    CIReport,
)
from promptci.registry import PromptRegistry
from promptci.gates import (
    BaseGate,
    LengthGate,
    VariableGate,
    InjectionRiskGate,
    KeywordCoverageGate,
    RegressionGatePipeline,
)
from promptci.diff import diff_prompts, diff_to_unified
from promptci.exceptions import (
    PromptCIError,
    PromptNotFoundError,
    VersionConflictError,
    RegressionGateError,
    ValidationError,
    RenderError,
)
from promptci.advanced import (
    PromptCache,
    PromptPipeline,
    PromptRule,
    PromptValidator,
    SchemaEvolver,
    ConfidenceScorer,
    PIIScrubber,
    RateLimiter,
    CancellationToken,
    abatch_register,
    batch_register,
    PromptProfiler,
    DriftDetector,
    CIReportExporter,
    stream_versions,
    versions_to_ndjson,
    PromptRegressionTracker,
    ScoreTrend,
    AuditLog,
    CostLedger,
    ModelRouter,
)

__version__ = "1.0.0"

__all__ = [
    # Models
    "PromptStatus", "PromptVersion", "PromptDiffResult", "GateResult", "CIReport",
    # Registry
    "PromptRegistry",
    # Gates
    "BaseGate", "LengthGate", "VariableGate", "InjectionRiskGate",
    "KeywordCoverageGate", "RegressionGatePipeline",
    # Diff
    "diff_prompts", "diff_to_unified",
    # Exceptions
    "PromptCIError", "PromptNotFoundError", "VersionConflictError",
    "RegressionGateError", "ValidationError", "RenderError",
    # Advanced
    "PromptCache", "PromptPipeline", "PromptRule", "PromptValidator",
    "SchemaEvolver", "ConfidenceScorer", "PIIScrubber",
    "RateLimiter", "CancellationToken", "abatch_register", "batch_register",
    "PromptProfiler", "DriftDetector", "CIReportExporter",
    "stream_versions", "versions_to_ndjson",
    "PromptRegressionTracker", "ScoreTrend",
    "AuditLog", "CostLedger", "ModelRouter",
]
