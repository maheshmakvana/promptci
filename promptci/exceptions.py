"""Exceptions for promptci."""


class PromptRegistryError(Exception):
    """Base exception for promptci."""


class PromptNotFoundError(PromptRegistryError):
    """Raised when a prompt version or name does not exist."""


class VersionConflictError(PromptRegistryError):
    """Raised when a version already exists and overwrite is disallowed."""


class RegressionGateError(PromptRegistryError):
    """Raised when a prompt fails a regression quality gate."""


class ValidationError(PromptRegistryError):
    """Raised when prompt metadata or content fails validation."""


class RenderError(PromptRegistryError):
    """Raised when template rendering fails."""
