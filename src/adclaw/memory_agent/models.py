# -*- coding: utf-8 -*-
"""Pydantic models for the Always-On Memory Agent."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid4() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Core domain models
# ---------------------------------------------------------------------------

MemoryType = Literal["user", "feedback", "project", "reference"]


class Memory(BaseModel):
    """A single memory entry."""

    id: str = Field(default_factory=_uuid4)
    content: str
    content_hash: str = ""
    source_type: Literal["mcp_tool", "skill", "chat", "file_inbox", "manual"] = "manual"
    memory_type: MemoryType = "user"
    source_id: str = ""
    entities: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    importance: float = 0.5
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_utcnow)
    updated_at: str = Field(default_factory=_utcnow)
    is_deleted: int = 0
    last_consolidated_at: Optional[str] = None
    last_verified_at: Optional[str] = None
    superseded_by: Optional[str] = None

    def compute_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()

    def model_post_init(self, _context: Any) -> None:
        if not self.content_hash:
            self.content_hash = self.compute_hash()


class Consolidation(BaseModel):
    """An insight derived from a cluster of related memories."""

    id: str = Field(default_factory=_uuid4)
    insight: str
    memory_ids: List[str] = Field(default_factory=list)
    importance: float = 0.5
    created_at: str = Field(default_factory=_utcnow)


class MemorySearchResult(BaseModel):
    """A single search result with score."""

    memory: Memory
    score: float = 0.0


class QueryResult(BaseModel):
    """Result returned by QueryAgent."""

    answer: str = ""
    citations: List[MemorySearchResult] = Field(default_factory=list)
    consolidations: List[Consolidation] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class AOMConfig(BaseModel):
    """Always-On Memory configuration (lives in AgentsConfig)."""

    enabled: bool = False
    embedding_backend: Literal["local", "api"] = "local"
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_api_url: str = ""
    embedding_dimensions: int = 384
    consolidation_interval_minutes: int = 60
    consolidation_enabled: bool = True
    auto_capture_mcp: bool = True
    auto_capture_skills: bool = True
    auto_capture_chat: bool = False
    file_inbox_enabled: bool = False
    importance_threshold: float = 0.3
    max_memories: int = 100_000

    # --- Consolidation v2: gate logic & contradiction detection ---
    consolidation_min_interval_seconds: int = 300
    consolidation_min_new_memories: int = 5
    staleness_decay_rate: float = 0.02
    staleness_min_weight: float = 0.5
    stale_verification_days: int = 14
    contradiction_detection_enabled: bool = True

    # --- Advanced multimodal mode ---
    # When multimodal_api_key is set, AOM can process images, audio, video, PDF
    # via a vision/multimodal LLM. Without it, only text files are supported.
    multimodal_provider: Literal["gemini", "openai", "anthropic"] = "gemini"
    multimodal_api_key: str = ""
    multimodal_model: str = ""  # empty = provider default (e.g. gemini-2.5-flash-lite)
    multimodal_api_url: str = ""  # custom endpoint override
