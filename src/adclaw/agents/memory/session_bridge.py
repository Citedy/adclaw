# -*- coding: utf-8 -*-
"""Cross-session context bridge.

Provides prior-knowledge injection so new sessions don't start cold.
Combines recent session summaries (with staleness cues) and AOM memories
into a structured section that fits within a token budget.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional

from ...memory_agent.tiers import estimate_tokens, generate_tiers

logger = logging.getLogger(__name__)

# Staleness thresholds in seconds
FRESH_THRESHOLD = 3600  # < 1 hour: "just now"
RECENT_THRESHOLD = 86400  # < 1 day: "earlier today" / "Xh ago"
STALE_THRESHOLD = 604800  # < 1 week: "Xd ago"
# > 1 week: "Xw ago (may be outdated)"


@dataclass
class SessionSummary:
    """Summary of a completed session for cross-session injection."""

    session_id: str
    timestamp: float  # unix epoch when session ended
    summary_text: str  # L1-tier summary of the session
    decisions: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    topic_tags: List[str] = field(default_factory=list)


def staleness_label(timestamp: float) -> str:
    """Human-readable staleness cue for a timestamp."""
    age = time.time() - timestamp
    if age < FRESH_THRESHOLD:
        return "just now"
    if age < RECENT_THRESHOLD:
        hours = max(1, int(age / 3600))
        return f"{hours}h ago"
    if age < STALE_THRESHOLD:
        days = max(1, int(age / 86400))
        return f"{days}d ago"
    weeks = max(1, int(age / 604800))
    return f"{weeks}w ago (may be outdated)"


def extract_tagged_lines(
    text: str,
    prefix: str,
) -> List[str]:
    """Extract lines starting with a given prefix (e.g. DECISION:, FAILED:).

    Args:
        text: Summary text to scan.
        prefix: Prefix to match (case-insensitive).

    Returns:
        List of matched line contents (prefix stripped).
    """
    results: List[str] = []
    upper_prefix = prefix.upper().rstrip(":") + ":"
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith(upper_prefix):
            results.append(stripped[len(upper_prefix) :].strip())
    return results


def build_session_summary(
    session_id: str,
    summary_text: str,
    topic_tags: Optional[List[str]] = None,
    timestamp: Optional[float] = None,
) -> SessionSummary:
    """Build a SessionSummary by extracting DECISION:/FAILED: lines.

    Args:
        session_id: Unique session identifier.
        summary_text: The topic-structured summary text.
        topic_tags: Optional list of topic names from clusters.
        timestamp: Session end time (defaults to now).

    Returns:
        SessionSummary with extracted decisions and failures.
    """
    return SessionSummary(
        session_id=session_id,
        timestamp=timestamp if timestamp is not None else time.time(),
        summary_text=summary_text,
        decisions=extract_tagged_lines(summary_text, "DECISION"),
        failures=extract_tagged_lines(summary_text, "FAILED"),
        topic_tags=topic_tags or [],
    )


def build_prior_knowledge_section(
    session_summaries: List[SessionSummary],
    aom_memories: List[str],
    token_budget: int = 2000,
) -> str:
    """Build a Prior Knowledge section for new session context.

    Combines:
    1. AOM memories (always fresh — they are curated).
    2. Recent session summaries (with staleness cues).

    Content is tiered to fit within token_budget.

    Args:
        session_summaries: Summaries from recent sessions, newest first.
        aom_memories: Relevant AOM memories for the current context.
        token_budget: Maximum tokens for the prior knowledge section.

    Returns:
        Formatted string ready for injection, or empty string if no content.
    """
    parts: List[str] = []

    # AOM memories first (highest signal, curated)
    if aom_memories:
        aom_section = "### Long-Term Memory\n" + "\n".join(
            f"- {mem}" for mem in aom_memories
        )
        parts.append(aom_section)

    # Recent session summaries with staleness
    for summary in session_summaries[:5]:
        staleness = staleness_label(summary.timestamp)
        header = f"### Session ({staleness})"

        lines = [header]
        if summary.decisions:
            lines.append("Decisions: " + "; ".join(summary.decisions))
        if summary.failures:
            lines.append("Failed approaches: " + "; ".join(summary.failures))
        lines.append(summary.summary_text)

        parts.append("\n".join(lines))

    if not parts:
        return ""

    full_text = "\n\n".join(parts)

    # Tier to fit budget
    custom_budgets = {
        "L0": token_budget // 4,
        "L1": token_budget // 2,
        "L2": token_budget,
    }
    tiers = generate_tiers(full_text, budgets=custom_budgets)

    # Pick the largest tier that fits
    for tier_name in ["L2", "L1", "L0"]:
        tier_text = tiers.get(tier_name, "")
        est_tokens = estimate_tokens(tier_text)
        if est_tokens <= token_budget:
            return f"## Prior Knowledge\n{tier_text}"

    return f"## Prior Knowledge\n{tiers.get('L0', '')}"
