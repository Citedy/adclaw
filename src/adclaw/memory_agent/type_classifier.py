# -*- coding: utf-8 -*-
"""Memory type classifier — keyword heuristics for classifying memories into types."""

from __future__ import annotations

import logging
from typing import Optional

from .models import MemoryType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword signals per type (checked in priority order)
# ---------------------------------------------------------------------------

_SIGNALS: dict[MemoryType, list[str]] = {
    "feedback": [
        "don't", "dont", "never", "stop doing", "wrong", "instead of",
        "not allowed", "forbidden", "avoid", "do not", "should not",
        "please don't", "that's wrong", "incorrect", "fix this",
        "stop using", "change to", "replace with",
    ],
    "project": [
        "deadline", "by monday", "by friday", "due date", "launch",
        "campaign", "sprint", "milestone", "scheduled for", "meeting",
        "client wants", "stakeholder", "deliverable", "priority",
        "task", "project", "roadmap", "timeline", "before march",
        "before april", "q1", "q2", "q3", "q4",
    ],
    "reference": [
        "http://", "https://", "drive.google", "notion.so", "figma.com",
        "docs/", "confluence", "jira", "linear.app", "slack.com",
        "the doc at", "see link", "reference:", "wiki", "handbook",
        "guidelines at", "brand guide", "style guide",
    ],
    "user": [
        "i prefer", "i like", "i want", "i always", "my style",
        "my preference", "i usually", "i tend to", "my background",
        "i'm a", "i am a", "my role", "my expertise",
    ],
}

# Priority order for tie-breaking (feedback wins ties)
_PRIORITY: list[MemoryType] = ["feedback", "project", "reference", "user"]


def classify_memory_type(content: str, metadata: Optional[dict] = None) -> MemoryType:
    """Classify memory content into one of four types using keyword heuristics.

    Priority order: feedback > project > reference > user (default).
    Feedback is highest priority because corrections must never be missed.

    Args:
        content: The memory content text.
        metadata: Optional metadata dict (may contain explicit type hint).

    Returns:
        The classified MemoryType.
    """
    # Explicit override from metadata
    _VALID_TYPES = {"user", "feedback", "project", "reference"}
    if metadata and metadata.get("memory_type") in _VALID_TYPES:
        return metadata["memory_type"]

    lower = content.lower()

    # Score each type by keyword hits
    scores: dict[MemoryType, int] = {mtype: 0 for mtype in _SIGNALS}
    for mtype, signals in _SIGNALS.items():
        for signal in signals:
            if signal in lower:
                scores[mtype] += 1

    # Pick highest scoring type; priority order breaks ties
    best_type: MemoryType = "user"
    best_score = 0
    for mtype in _PRIORITY:
        if scores[mtype] > best_score:
            best_score = scores[mtype]
            best_type = mtype

    return best_type


# Markers for extracting feedback structure components
_REASON_MARKERS = ["because", "reason:", "since", "due to"]
_APPLICATION_MARKERS = ["instead", "apply", "do this:"]


def extract_feedback_structure(content: str) -> Optional[dict]:
    """Extract rule/reason/application structure from feedback content.

    Returns dict with keys: rule, reason, application. Or None if not parseable.
    """
    lower = content.lower()

    rule = content.split(".")[0].strip() if "." in content else content.strip()
    reason = ""
    application = ""

    for marker in _REASON_MARKERS:
        if marker in lower:
            idx = lower.index(marker)
            after = content[idx + len(marker):].strip()
            reason = after.split(".")[0].strip() if "." in after else after.strip()
            break

    for marker in _APPLICATION_MARKERS:
        if marker in lower:
            idx = lower.index(marker)
            after = content[idx + len(marker):].strip()
            application = after.split(".")[0].strip() if "." in after else after.strip()
            break

    if not reason and not application:
        return None

    return {
        "rule": rule[:200],
        "reason": reason[:200],
        "application": application[:200],
    }
