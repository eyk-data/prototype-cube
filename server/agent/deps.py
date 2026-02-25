"""Shared dependencies injected into pydantic-ai agents."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentDeps:
    """Pre-fetched context passed to every agent.run() call via deps=."""

    dataset: str = ""
    cube_meta_context: str = ""
    valid_members: set[str] | None = None
    # Dynamic system prompt — set per-call, read by @agent.instructions
    system_prompt: str = ""
