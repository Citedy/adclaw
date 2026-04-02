# -*- coding: utf-8 -*-
"""Topic-clustered summarization for smart compaction.

Groups messages by topic (via tool names and content keywords) and builds
a structured prompt for LLM summarization that preserves topic headers,
key decisions, and failure context.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from agentscope.message import Msg

from .importance import Importance, classify_importance, msg_text
from ...memory_agent.compressor import rule_compress

logger = logging.getLogger(__name__)


@dataclass
class TopicCluster:
    """A group of related messages around a single topic."""

    topic: str
    messages: List[Msg]
    max_importance: Importance
    has_failure: bool = False


# Tool names that hint at topic categories
_TOOL_TOPIC_MAP: Dict[str, str] = {
    "execute_shell_command": "shell-ops",
    "read_file": "file-ops",
    "write_file": "file-ops",
    "edit_file": "file-ops",
    "browser_use": "web-research",
    "send_email": "communication",
    "memory_search": "memory-ops",
    "patch_skill_script": "skill-management",
}


def _extract_tool_names(msg: Msg) -> List[str]:
    """Extract tool names from a message's content blocks."""
    names: List[str] = []
    if not isinstance(msg.content, list):
        return names
    for block in msg.content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            name = block.get("name", "")
            if name:
                names.append(name)
        elif hasattr(block, "name") and hasattr(block, "type"):
            if getattr(block, "type", None) == "tool_use":
                names.append(block.name)
    return names


def _extract_topic_hint(msg: Msg) -> Optional[str]:
    """Extract a topic hint from a message based on tool calls or content."""
    tool_names = _extract_tool_names(msg)
    for fn_name in tool_names:
        if fn_name in _TOOL_TOPIC_MAP:
            return _TOOL_TOPIC_MAP[fn_name]
    if tool_names:
        return f"skill:{tool_names[0]}"

    content = msg_text(msg)
    lower = content.lower()

    _CONTENT_TOPIC_MAP = {
        "configuration": ["config", "setting", "parameter", "env"],
        "deployment": ["deploy", "docker", "build", "release"],
        "debugging": ["error", "bug", "fix", "debug", "traceback"],
        "testing": ["test", "assert", "expect", "verify"],
    }
    for topic, keywords in _CONTENT_TOPIC_MAP.items():
        if any(kw in lower for kw in keywords):
            return topic

    return None


def _build_cluster(topic: str, messages: List[Msg]) -> TopicCluster:
    """Build a TopicCluster with computed metadata."""
    importances = [classify_importance(m) for m in messages]
    has_failure = any(
        "fail" in msg_text(m).lower() or "error" in msg_text(m).lower()
        for m in messages
    )
    return TopicCluster(
        topic=topic,
        messages=messages,
        max_importance=max(importances),
        has_failure=has_failure,
    )


def cluster_by_topic(messages: List[Msg]) -> List[TopicCluster]:
    """Group messages into topic clusters.

    Uses a sliding-window approach: consecutive messages with the same
    topic hint are grouped together. Messages without a clear topic
    inherit the topic of their neighbors.
    """
    if not messages:
        return []

    # First pass: assign topic hints
    hints: List[Optional[str]] = [_extract_topic_hint(m) for m in messages]

    # Forward fill
    for i in range(1, len(hints)):
        if hints[i] is None:
            hints[i] = hints[i - 1]
    # Backward fill for leading Nones
    for i in range(len(hints) - 2, -1, -1):
        if hints[i] is None:
            hints[i] = hints[i + 1]
    # Any remaining Nones become "general"
    resolved_hints: List[str] = [h or "general" for h in hints]

    # Group consecutive same-topic messages
    clusters: List[TopicCluster] = []
    current_topic = resolved_hints[0]
    current_msgs: List[Msg] = [messages[0]]

    for i in range(1, len(messages)):
        if resolved_hints[i] == current_topic:
            current_msgs.append(messages[i])
        else:
            clusters.append(_build_cluster(current_topic, current_msgs))
            current_topic = resolved_hints[i]
            current_msgs = [messages[i]]

    if current_msgs:
        clusters.append(_build_cluster(current_topic, current_msgs))

    return clusters


def build_structured_summary_prompt(
    clusters: List[TopicCluster],
    previous_summary: str = "",
) -> str:
    """Build summarization context for compact_memory.

    Produces instructions + prior context only (NOT message
    content) — compact_memory receives messages separately.
    """
    sections: List[str] = []

    if previous_summary:
        sections.append(
            "## Prior Context (from earlier compaction)\n"
            f"{rule_compress(previous_summary)}"
        )

    # Topic map: tell the LLM how messages are grouped
    topic_lines: List[str] = []
    for cluster in clusters:
        importance_label = cluster.max_importance.name
        failure_marker = " [CONTAINS FAILURES]" if cluster.has_failure else ""
        topic_lines.append(
            f"- {cluster.topic} ({len(cluster.messages)} messages, "
            f"importance: {importance_label}){failure_marker}"
        )
    if topic_lines:
        sections.append("## Topic Map\n" + "\n".join(topic_lines))

    instructions = (
        "Summarize the conversation messages by topic. "
        "For each topic section:\n"
        "1. State the key outcome or decision "
        "(prefix with DECISION:).\n"
        "2. List actions taken or pending "
        "(prefix with ACTION:).\n"
        "3. Note what was tried and failed "
        "(prefix with FAILED:).\n"
        "4. Preserve exact entity names "
        "(paths, URLs, configs, models).\n"
        "5. Keep the topic headers.\n"
        "6. For LOW topics, one sentence max."
    )

    if sections:
        return instructions + "\n\n" + "\n\n".join(sections)
    return instructions
