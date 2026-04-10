"""Prompt diff utilities."""
from __future__ import annotations

import difflib
import json
from typing import List

from promptci.models import PromptDiffResult, PromptVersion


def diff_prompts(a: PromptVersion, b: PromptVersion) -> PromptDiffResult:
    """Compute line-level diff between two prompt versions."""
    a_lines = a.content.splitlines(keepends=True)
    b_lines = b.content.splitlines(keepends=True)
    added: List[str] = []
    removed: List[str] = []

    for group in difflib.SequenceMatcher(None, a_lines, b_lines).get_grouped_opcodes(n=3):
        for tag, i1, i2, j1, j2 in group:
            if tag in ("replace", "delete"):
                removed.extend(a_lines[i1:i2])
            if tag in ("replace", "insert"):
                added.extend(b_lines[j1:j2])

    return PromptDiffResult(
        name=a.name,
        version_a=a.version,
        version_b=b.version,
        added_lines=[l.rstrip() for l in added],
        removed_lines=[l.rstrip() for l in removed],
        changed=bool(added or removed),
        char_delta=len(b.content) - len(a.content),
    )


def diff_to_unified(a: PromptVersion, b: PromptVersion) -> str:
    """Return a unified-diff string between two prompt versions."""
    return "".join(
        difflib.unified_diff(
            a.content.splitlines(keepends=True),
            b.content.splitlines(keepends=True),
            fromfile=f"{a.name} v{a.version}",
            tofile=f"{b.name} v{b.version}",
        )
    )
