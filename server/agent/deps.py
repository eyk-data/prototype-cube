"""Shared dependencies injected into pydantic-ai agents."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentDeps:
    """Pre-fetched context passed to every agent.run() call via deps=."""

    cube_meta_context: str = ""
    valid_members: set[str] | None = None
