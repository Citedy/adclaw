# -*- coding: utf-8 -*-
"""Message importance classification for smart compaction.

Classifies messages into importance tiers (CRITICAL → TRIVIAL) using
pattern matching on content and role. Classification is stateless and
cheap — designed to run at compaction time, not at ingestion.
"""

from __future__ import annotations

import re
from enum import IntEnum
from typing import Dict, List

from agentscope.message import Msg


class Importance(IntEnum):
    """Message importance levels. Higher = survives longer in context."""

    CRITICAL = 5  # User decisions, config changes, explicit instructions
    HIGH = 4  # Errors, warnings, failed attempts, action items
    MEDIUM = 3  # Tool results with meaningful output, task progress
    LOW = 2  # Acknowledgments, status checks, routine output
    TRIVIAL = 1  # Greetings, small talk, empty/minimal responses


# Patterns that signal importance (compiled once at import)
_CRITICAL_PATTERNS: List[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\b(decided|decision|chose|choose|approved|rejected)\b",
        r"\b(config(?:ure|uration)?|setting|parameter)"
        r"\s*(?:changed?|updated?|set)\b",
        r"\b(never|always|must|critical|important)\b"
        r".*\b(do|use|avoid|remember)\b",
        r"\b(from now on|going forward|new rule)\b",
        r"/compact|/new|/reset",
    ]
]

_HIGH_PATTERNS: List[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\b(error|exception|traceback|failed|failure|bug)\b",
        r"\b(warning|caution|don't|avoid|broke|broken)\b",
        r"\b(fix(?:ed)?|resolved|workaround|rollback)\b",
        r"\b(todo|action item|next step|blocker)\b",
        r"\b(tried|attempted|didn't work|won't work)\b",
    ]
]

_LOW_PATTERNS: List[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"^(ok|okay|sure|thanks|got it|understood|ack)\b",
        r"^(yes|no|right|correct|exactly)\s*[.!]?\s*$",
        r"^\s*(done|ready|noted)\s*[.!]?\s*$",
    ]
]


def msg_text(msg: Msg) -> str:
    """Extract text content from a Msg."""
    if hasattr(msg, "get_text_content"):
        return msg.get_text_content() or ""
    return str(msg.content or "")


def _has_tool_blocks(msg: Msg) -> bool:
    """Check if message contains tool use/result blocks."""
    if not isinstance(msg.content, list):
        return False
    for block in msg.content:
        if isinstance(block, dict) and block.get("type") in (
            "tool_use",
            "tool_result",
        ):
            return True
        if hasattr(block, "type") and block.type in (
            "tool_use",
            "tool_result",
        ):
            return True
    return False


def classify_importance(msg: Msg) -> Importance:
    """Classify a message's importance based on content and role.

    Rules applied in priority order:
    1. System messages are always CRITICAL.
    2. Pattern matching on content for CRITICAL/HIGH/LOW.
    3. Tool call messages default to MEDIUM.
    4. Everything else defaults to MEDIUM.
    """
    content = msg_text(msg)
    role = getattr(msg, "role", "user")

    is_critical = role == "system" or any(
        p.search(content) for p in _CRITICAL_PATTERNS
    )
    if is_critical:
        return Importance.CRITICAL

    for pattern in _HIGH_PATTERNS:
        if pattern.search(content):
            return Importance.HIGH

    # Only match LOW patterns on short messages to avoid false positives
    if len(content) < 100:
        for pattern in _LOW_PATTERNS:
            if pattern.search(content):
                return Importance.LOW

    if _has_tool_blocks(msg):
        return Importance.MEDIUM

    # Short/empty messages: TRIVIAL if < 5 chars, LOW if short assistant
    stripped = content.strip()
    if len(stripped) < 5:
        return Importance.TRIVIAL

    return (
        Importance.LOW
        if len(stripped) < 15 and role == "assistant"
        else Importance.MEDIUM
    )


def tag_messages(messages: List[Msg]) -> Dict[str, Importance]:
    """Tag a list of messages with importance scores.

    Returns:
        Dict mapping msg.id to Importance level.
    """
    return {msg.id: classify_importance(msg) for msg in messages}
