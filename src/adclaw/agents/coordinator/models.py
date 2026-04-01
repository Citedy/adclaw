# -*- coding: utf-8 -*-
"""Coordinator data models — TaskStrategy, PersonaOutcome, NextStep."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


class PersonaOutcome(BaseModel):
    """Summary of a single persona execution within a strategy."""

    persona_id: str
    task_given: str
    status: Literal["success", "partial", "failed", "stuck", "pending"] = "pending"
    key_findings: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    iteration: int = 0
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class NextStep(BaseModel):
    """A specific next action the coordinator has decided on."""

    persona_id: str
    task: str
    rationale: str
    priority: int = 1  # 1 = highest
    depends_on: Optional[str] = None  # forward-looking: persona_id that must finish first


class TaskStrategy(BaseModel):
    """A multi-step strategy the coordinator maintains across cron cycles.

    Stored in AOM with source_type='manual' and metadata
    {"coordinator_strategy": True}. Memory.source_type is a
    Literal enum ("mcp_tool"|"skill"|"chat"|"file_inbox"|"manual"),
    so custom source types are not supported — use metadata instead.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: str
    status: Literal["active", "completed", "abandoned"] = "active"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    outcomes: list[PersonaOutcome] = Field(default_factory=list)
    next_steps: list[NextStep] = Field(default_factory=list)
    synthesis: str = ""  # coordinator's analysis of the current state

    # Pivot tracking
    pivot_count: int = 0
    max_pivots: int = 3  # abandon after N pivots on same goal

    def add_outcome(self, outcome: PersonaOutcome) -> None:
        self.outcomes.append(outcome)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def should_pivot(self, persona_id: str) -> bool:
        """Check if a persona has been stuck/failed enough to warrant a pivot."""
        recent = [
            o
            for o in self.outcomes
            if o.persona_id == persona_id and o.status in ("failed", "stuck")
        ]
        return len(recent) >= 2

    def should_abandon(self) -> bool:
        return self.pivot_count >= self.max_pivots
