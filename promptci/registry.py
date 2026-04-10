"""Core prompt version registry."""
from __future__ import annotations

import json
import logging
import re
import threading
from typing import Dict, List, Optional

from promptci.exceptions import PromptNotFoundError, VersionConflictError, ValidationError
from promptci.models import PromptStatus, PromptVersion

logger = logging.getLogger(__name__)

_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


class PromptRegistry:
    """Thread-safe, in-memory prompt version registry with persistence."""

    def __init__(self) -> None:
        # name → version_str → PromptVersion
        self._store: Dict[str, Dict[str, PromptVersion]] = {}
        self._lock = threading.RLock()

    # ── Write ──────────────────────────────────────────────────────────

    def register(self, prompt: PromptVersion, overwrite: bool = False) -> None:
        """Register a new prompt version."""
        variables = list({m for m in _VAR_PATTERN.findall(prompt.content)})
        prompt = prompt.model_copy(update={"variables": variables})

        with self._lock:
            if prompt.name not in self._store:
                self._store[prompt.name] = {}
            if prompt.version in self._store[prompt.name] and not overwrite:
                raise VersionConflictError(
                    f"Prompt '{prompt.name}' v{prompt.version} already exists. "
                    "Use overwrite=True to replace."
                )
            self._store[prompt.name][prompt.version] = prompt
        logger.info("Registered prompt '%s' v%s (status=%s)", prompt.name, prompt.version, prompt.status)

    def set_status(self, name: str, version: str, status: PromptStatus) -> None:
        """Update the lifecycle status of a prompt version."""
        with self._lock:
            pv = self._get(name, version)
            self._store[name][version] = pv.model_copy(update={"status": status})
        logger.info("Set '%s' v%s status → %s", name, version, status)

    # ── Read ───────────────────────────────────────────────────────────

    def get(self, name: str, version: Optional[str] = None) -> PromptVersion:
        """Retrieve a prompt version. Defaults to the latest active version."""
        with self._lock:
            return self._get(name, version)

    def _get(self, name: str, version: Optional[str] = None) -> PromptVersion:
        if name not in self._store:
            raise PromptNotFoundError(f"Prompt '{name}' not found")
        versions = self._store[name]
        if version is not None:
            if version not in versions:
                raise PromptNotFoundError(f"Prompt '{name}' v{version} not found")
            return versions[version]
        # Auto-select: prefer latest active, else latest any
        active = [v for v in versions.values() if v.status == PromptStatus.ACTIVE]
        pool = active if active else list(versions.values())
        return sorted(pool, key=lambda v: v.created_at)[-1]

    def list_versions(self, name: str) -> List[PromptVersion]:
        """Return all versions of a named prompt, sorted by creation time."""
        with self._lock:
            if name not in self._store:
                raise PromptNotFoundError(f"Prompt '{name}' not found")
            return sorted(self._store[name].values(), key=lambda v: v.created_at)

    def list_prompts(self) -> List[str]:
        """Return all registered prompt names."""
        with self._lock:
            return list(self._store.keys())

    # ── Render ─────────────────────────────────────────────────────────

    def render(self, name: str, variables: Dict[str, str], version: Optional[str] = None) -> str:
        """Render a prompt with variable substitution."""
        pv = self.get(name, version)
        rendered = pv.content
        for var, val in variables.items():
            rendered = rendered.replace(f"{{{{{var}}}}}", val)
        missing = _VAR_PATTERN.findall(rendered)
        if missing:
            raise ValidationError(f"Unresolved variables in '{name}': {missing}")
        return rendered

    # ── Persistence ────────────────────────────────────────────────────

    def save(self, path: str) -> None:
        """Persist registry to JSON."""
        with self._lock:
            data = {
                name: {v: pv.model_dump() for v, pv in versions.items()}
                for name, versions in self._store.items()
            }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("Registry saved to %s", path)

    def load(self, path: str) -> None:
        """Load registry from JSON."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        with self._lock:
            for name, versions in data.items():
                self._store[name] = {v: PromptVersion(**pv) for v, pv in versions.items()}
        logger.info("Registry loaded from %s", path)
