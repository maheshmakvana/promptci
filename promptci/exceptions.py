"""Exceptions for promptci."""


class PromptCIError(Exception):
    """Base exception for promptci."""


class PromptNotFoundError(PromptCIError):
    """Raised when a prompt version or name does not exist."""


class VersionConflictError(PromptCIError):
    """Raised when a version already exists and overwrite is disallowed."""


class RegressionGateError(PromptCIError):
    """Raised when a prompt fails a regression quality gate."""


class ValidationError(PromptCIError):
    """Raised when prompt metadata or content fails validation."""


class RenderError(PromptCIError):
    """Raised when template rendering fails."""
