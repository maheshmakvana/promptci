"""Pydantic models for promptci."""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PromptStatus(str, Enum):
    """Lifecycle status of a prompt version."""
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class PromptVersion(BaseModel):
    """A single versioned prompt."""
    name: str
    version: str              # semver string e.g. "1.2.0"
    content: str              # raw prompt text (may contain {{variable}} placeholders)
    variables: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    status: PromptStatus = PromptStatus.DRAFT
    author: Optional[str] = None
    description: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PromptDiffResult(BaseModel):
    """Diff between two prompt versions."""
    name: str
    version_a: str
    version_b: str
    added_lines: List[str]
    removed_lines: List[str]
    changed: bool
    char_delta: int


class GateResult(BaseModel):
    """Result of a regression gate check."""
    prompt_name: str
    version: str
    gate_name: str
    passed: bool
    score: float
    threshold: float
    message: str


class CIReport(BaseModel):
    """Full CI/CD pipeline report for a prompt."""
    prompt_name: str
    version: str
    gates: List[GateResult]
    overall_passed: bool
    timestamp: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)
