# -*- coding: utf-8 -*-
"""Tests for 2c: Session Context Management — Smart Compaction.

Covers all 4 modules:
- importance.py: message importance classification
- tiered_compaction.py: L0/L1/L2 survival logic
- topic_summarizer.py: topic clustering + structured prompts
- session_bridge.py: cross-session context injection
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List

from adclaw.agents.memory.importance import (
    Importance,
    classify_importance,
    tag_messages,
)
from adclaw.agents.memory.tiered_compaction import (
    IMPORTANCE_TO_TIER,
    plan_compaction,
)
from adclaw.agents.memory.topic_summarizer import (
    TopicCluster,
    build_structured_summary_prompt,
    cluster_by_topic,
)
from adclaw.agents.memory.session_bridge import (
    SessionSummary,
    build_prior_knowledge_section,
    build_session_summary,
    extract_tagged_lines,
    staleness_label,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeMsg:
    """Minimal Msg stand-in for testing."""

    id: str = "test"
    role: str = "user"
    content: str | list = ""

    def get_text_content(self) -> str:
        if self.content is None:
            return ""
        if isinstance(self.content, str):
            return self.content
        # Extract text from content blocks
        parts: List[str] = []
        for block in self.content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
        return " ".join(parts)


def _msg(
    content: str = "",
    role: str = "user",
    msg_id: str = "test",
) -> FakeMsg:
    return FakeMsg(id=msg_id, role=role, content=content)


def _tool_msg(
    tool_name: str = "execute_shell_command",
    msg_id: str = "tool1",
) -> FakeMsg:
    return FakeMsg(
        id=msg_id,
        role="assistant",
        content=[{"type": "tool_use", "name": tool_name, "input": {}}],
    )


# ===================================================================
# 1. Importance Classification
# ===================================================================


class TestClassifyImportance:
    def test_system_messages_always_critical(self):
        msg = _msg("You are a helpful assistant", role="system")
        assert classify_importance(msg) == Importance.CRITICAL

    def test_decision_keywords(self):
        msg = _msg("I decided to use glm-5 for production")
        assert classify_importance(msg) == Importance.CRITICAL

    def test_config_change_is_critical(self):
        msg = _msg("Config changed: max_input_length set to 64000")
        assert classify_importance(msg) == Importance.CRITICAL

    def test_never_avoid_rule(self):
        msg = _msg("Never use qwen-max, always use glm-5 to avoid timeouts")
        assert classify_importance(msg) == Importance.CRITICAL

    def test_from_now_on_is_critical(self):
        msg = _msg("From now on, deploy to staging first")
        assert classify_importance(msg) == Importance.CRITICAL

    def test_error_is_high(self):
        msg = _msg("Error: connection refused on port 8088")
        assert classify_importance(msg) == Importance.HIGH

    def test_failed_attempt_is_high(self):
        msg = _msg("Tried qwen-max but it didn't work on Coding Plan")
        assert classify_importance(msg) == Importance.HIGH

    def test_fix_is_high(self):
        msg = _msg("Fixed the deployment script issue")
        assert classify_importance(msg) == Importance.HIGH

    def test_todo_is_high(self):
        msg = _msg("TODO: update the API key before next deploy")
        assert classify_importance(msg) == Importance.HIGH

    def test_acknowledgment_is_low(self):
        msg = _msg("ok thanks", role="user")
        assert classify_importance(msg) == Importance.LOW

    def test_yes_is_low(self):
        msg = _msg("yes", role="user")
        assert classify_importance(msg) == Importance.LOW

    def test_done_is_low(self):
        msg = _msg("done", role="user")
        assert classify_importance(msg) == Importance.LOW

    def test_short_assistant_response_is_low(self):
        msg = _msg("Done.", role="assistant")
        assert classify_importance(msg) == Importance.LOW

    def test_normal_message_is_medium(self):
        msg = _msg("Can you help me set up the deployment pipeline?")
        assert classify_importance(msg) == Importance.MEDIUM

    def test_tool_message_is_medium(self):
        msg = _tool_msg()
        assert classify_importance(msg) == Importance.MEDIUM

    def test_long_low_pattern_not_matched(self):
        # "ok" at start but message is > 100 chars — should not match LOW
        msg = _msg("ok " + "x" * 100, role="user")
        assert classify_importance(msg) == Importance.MEDIUM

    def test_slash_command_is_critical(self):
        msg = _msg("/compact the memory")
        assert classify_importance(msg) == Importance.CRITICAL

    def test_empty_message_is_trivial(self):
        msg = _msg("", role="user")
        assert classify_importance(msg) == Importance.TRIVIAL

    def test_whitespace_only_is_trivial(self):
        msg = _msg("  ", role="assistant")
        assert classify_importance(msg) == Importance.TRIVIAL

    def test_single_char_is_trivial(self):
        msg = _msg(".", role="user")
        assert classify_importance(msg) == Importance.TRIVIAL


class TestTagMessages:
    def test_returns_dict_with_correct_ids(self):
        msgs = [
            _msg("decided to use X", msg_id="1"),
            _msg("ok", msg_id="2"),
            _msg("error in build", msg_id="3"),
        ]
        tags = tag_messages(msgs)
        assert tags["1"] == Importance.CRITICAL
        assert tags["2"] == Importance.LOW
        assert tags["3"] == Importance.HIGH

    def test_empty_list(self):
        assert tag_messages([]) == {}


# ===================================================================
# 2. Tiered Compaction
# ===================================================================


class TestTieredCompaction:
    def test_l2_compacted_immediately(self):
        msgs = [
            _msg("ok thanks", msg_id="ack1"),
            _msg("sure", msg_id="ack2"),
            _msg("I decided to use glm-5", msg_id="decision1"),
        ]
        plan = plan_compaction(
            messages=msgs,
            cycle_counts={"ack1": 0, "ack2": 0, "decision1": 0},
            current_cycle=0,
        )
        compact_ids = {m.id for m in plan.to_compact}
        assert "ack1" in compact_ids
        assert "ack2" in compact_ids
        # L0 (CRITICAL) preserved
        assert "decision1" not in compact_ids

    def test_l1_survives_two_cycles(self):
        msgs = [_msg("Error: connection failed", msg_id="err1")]

        # Cycle 0: should survive
        plan = plan_compaction(msgs, {"err1": 0}, current_cycle=0)
        assert len(plan.to_compact) == 0

        # Cycle 1: should still survive
        plan = plan_compaction(msgs, {"err1": 0}, current_cycle=1)
        assert len(plan.to_compact) == 0

        # Cycle 2: should be compacted
        plan = plan_compaction(msgs, {"err1": 0}, current_cycle=2)
        assert len(plan.to_compact) == 1

    def test_l0_never_compacted(self):
        msgs = [_msg("I decided to deploy to production", msg_id="d1")]
        plan = plan_compaction(msgs, {"d1": 0}, current_cycle=100)
        assert len(plan.to_compact) == 0
        assert len(plan.to_preserve) == 1

    def test_new_messages_default_to_current_cycle(self):
        msgs = [_msg("ok", msg_id="new1")]
        # Not in cycle_counts — defaults to current_cycle
        plan = plan_compaction(msgs, {}, current_cycle=5)
        # L2 with age=0, survival=0 → compacted
        compact_ids = {m.id for m in plan.to_compact}
        assert "new1" in compact_ids

    def test_stats_populated(self):
        msgs = [
            _msg("decided X", msg_id="c1"),
            _msg("error Y", msg_id="h1"),
            _msg("ok", msg_id="l1"),
        ]
        plan = plan_compaction(msgs, {}, current_cycle=0)
        assert plan.stats["total"] == 3
        assert plan.stats["tier_L0"] == 1
        assert plan.stats["tier_L1"] == 1
        assert plan.stats["tier_L2"] == 1

    def test_empty_messages(self):
        plan = plan_compaction([], {}, current_cycle=0)
        assert plan.to_compact == []
        assert plan.to_preserve == []

    def test_importance_to_tier_complete(self):
        for imp in Importance:
            assert imp in IMPORTANCE_TO_TIER


# ===================================================================
# 3. Topic Clustering & Summarization
# ===================================================================


class TestTopicClustering:
    def test_groups_consecutive_same_topic(self):
        msgs = [
            _msg("There's a bug in the config", msg_id="1"),
            _msg("Error: missing key in config.json", msg_id="2"),
            _msg("Let me deploy the fix", msg_id="3"),
        ]
        clusters = cluster_by_topic(msgs)
        assert len(clusters) >= 1
        # All messages should be covered
        total = sum(len(c.messages) for c in clusters)
        assert total == 3

    def test_failure_detection(self):
        msgs = [_msg("Tried X but it failed with error Y", msg_id="1")]
        clusters = cluster_by_topic(msgs)
        assert clusters[0].has_failure is True

    def test_no_failure_when_clean(self):
        msgs = [_msg("Deployed the new version successfully", msg_id="1")]
        clusters = cluster_by_topic(msgs)
        assert clusters[0].has_failure is False

    def test_tool_messages_clustered(self):
        msgs = [
            _tool_msg("read_file", msg_id="t1"),
            _tool_msg("write_file", msg_id="t2"),
            _msg("Checking the tests", msg_id="m1"),
        ]
        clusters = cluster_by_topic(msgs)
        # First two should be in "file-ops" cluster
        assert clusters[0].topic == "file-ops"
        assert len(clusters[0].messages) == 2

    def test_empty_messages(self):
        assert not cluster_by_topic([])

    def test_single_message(self):
        msgs = [_msg("hello world", msg_id="1")]
        clusters = cluster_by_topic(msgs)
        assert len(clusters) == 1
        assert clusters[0].topic == "general"

    def test_general_fallback_when_no_hints(self):
        msgs = [
            _msg("How are you?", msg_id="1"),
            _msg("I'm fine", msg_id="2"),
        ]
        clusters = cluster_by_topic(msgs)
        assert all(c.topic == "general" for c in clusters)


class TestStructuredSummaryPrompt:
    def test_basic_prompt_structure(self):
        cluster = TopicCluster(
            topic="debugging",
            messages=[_msg("Error in deployment", msg_id="1")],
            max_importance=Importance.HIGH,
            has_failure=True,
        )
        prompt = build_structured_summary_prompt([cluster])
        assert "debugging" in prompt
        assert "[CONTAINS FAILURES]" in prompt
        assert "DECISION:" in prompt
        assert "FAILED:" in prompt
        assert "Topic Map" in prompt

    def test_previous_summary_included(self):
        cluster = TopicCluster(
            topic="general",
            messages=[_msg("hello", msg_id="1")],
            max_importance=Importance.MEDIUM,
        )
        prompt = build_structured_summary_prompt(
            [cluster],
            previous_summary="User was working on deployment",
        )
        assert "Prior Context" in prompt
        assert "deployment" in prompt

    def test_no_message_content_in_prompt(self):
        """Prompt should NOT embed message content to avoid double tokens."""
        cluster = TopicCluster(
            topic="general",
            messages=[_msg("secret message content xyz", msg_id="1")],
            max_importance=Importance.MEDIUM,
        )
        prompt = build_structured_summary_prompt([cluster])
        assert "secret message content xyz" not in prompt
        assert "1 messages" in prompt

    def test_empty_clusters(self):
        prompt = build_structured_summary_prompt([])
        assert "Summarize" in prompt


# ===================================================================
# 4. Session Bridge
# ===================================================================


class TestStalenessLabel:
    def test_just_now(self):
        assert staleness_label(time.time() - 60) == "just now"

    def test_hours_ago(self):
        label = staleness_label(time.time() - 7200)
        assert "h ago" in label

    def test_days_ago(self):
        label = staleness_label(time.time() - 172800)
        assert "d ago" in label

    def test_weeks_ago_outdated(self):
        label = staleness_label(time.time() - 1209600)
        assert "outdated" in label

    def test_minimum_1h(self):
        label = staleness_label(time.time() - 3700)
        assert label == "1h ago"

    def test_minimum_1d(self):
        label = staleness_label(time.time() - 90000)
        assert label == "1d ago"


class TestExtractTaggedLines:
    def test_extracts_decisions(self):
        text = (
            "Some intro\nDECISION: Use glm-5\n"
            "More text\nDECISION: Deploy to staging"
        )
        decisions = extract_tagged_lines(text, "DECISION")
        assert decisions == ["Use glm-5", "Deploy to staging"]

    def test_case_insensitive(self):
        text = "decision: lowercase works too"
        assert extract_tagged_lines(text, "DECISION") == [
            "lowercase works too"
        ]

    def test_no_matches(self):
        assert not extract_tagged_lines("no tagged lines here", "DECISION")

    def test_failed_prefix(self):
        text = "FAILED: qwen-max on coding plan"
        assert extract_tagged_lines(text, "FAILED") == [
            "qwen-max on coding plan"
        ]


class TestBuildSessionSummary:
    def test_extracts_decisions_and_failures(self):
        text = (
            "## Topic: config\n"
            "DECISION: Use glm-5 for speed\n"
            "FAILED: qwen-max timed out\n"
            "ACTION: Update API key"
        )
        summary = build_session_summary(
            session_id="s1",
            summary_text=text,
            topic_tags=["config"],
        )
        assert summary.session_id == "s1"
        assert any("glm-5 for speed" in d for d in summary.decisions)
        assert "qwen-max timed out" in summary.failures
        assert summary.topic_tags == ["config"]
        assert summary.timestamp > 0

    def test_custom_timestamp(self):
        summary = build_session_summary("s1", "text", timestamp=1000.0)
        assert summary.timestamp == 1000.0


class TestBuildPriorKnowledge:
    def test_empty_inputs(self):
        result = build_prior_knowledge_section([], [])
        assert result == ""

    def test_aom_memories_included(self):
        result = build_prior_knowledge_section(
            session_summaries=[],
            aom_memories=["glm-5 is 6x faster than qwen3.5-plus"],
        )
        assert "glm-5" in result
        assert "Prior Knowledge" in result

    def test_session_summaries_with_staleness(self):
        summary = SessionSummary(
            session_id="s1",
            timestamp=time.time() - 60,
            summary_text="Worked on deployment",
            decisions=["Use Docker"],
            failures=["Nginx config failed"],
        )
        result = build_prior_knowledge_section([summary], [])
        assert "just now" in result
        assert "Use Docker" in result
        assert "Nginx config failed" in result

    def test_respects_token_budget(self):
        long_memories = [f"Memory item {i} " * 50 for i in range(20)]
        result = build_prior_knowledge_section(
            [],
            long_memories,
            token_budget=100,
        )
        # Should be tiered down to fit
        est_tokens = len(result) // 4
        assert est_tokens <= 200  # some overhead tolerance

    def test_max_5_sessions(self):
        summaries = [
            SessionSummary(
                session_id=f"s{i}",
                timestamp=time.time() - i * 3600,
                summary_text=f"Session {i}",
            )
            for i in range(10)
        ]
        result = build_prior_knowledge_section(summaries, [])
        # Should only include first 5
        assert "Session 0" in result
        assert "Session 4" in result
        # Session 5+ should not be present
        assert "Session 5" not in result


# ===================================================================
# 5. Critical Gap Tests
# ===================================================================


class TestClassifyImportanceNoneAndEmptyContent:
    """Gap #4: None/empty content in classify_importance.

    Messages with None content or content that returns None from
    get_text_content must not crash and should classify gracefully.
    """

    def test_none_content_does_not_crash(self):
        """msg_text() guards with `or ""` but we need to verify the
        full classify_importance path handles the resulting empty string."""
        msg = FakeMsg(id="n1", role="user", content=None)
        # content=None -> get_text_content returns None ->
        # msg_text should return ""
        result = classify_importance(msg)
        assert result == Importance.TRIVIAL

    def test_content_list_with_no_text_blocks(self):
        """Content is a list but contains no extractable text."""
        msg = FakeMsg(
            id="n2",
            role="assistant",
            content=[{"type": "image", "url": "http://example.com/img.png"}],
        )
        result = classify_importance(msg)
        # get_text_content returns "" for a list with no text blocks
        assert result == Importance.TRIVIAL

    def test_content_list_with_empty_strings(self):
        msg = FakeMsg(id="n3", role="user", content=["", ""])
        result = classify_importance(msg)
        assert result == Importance.TRIVIAL

    def test_none_returning_get_text_content(self):
        """Simulate a Msg subclass whose get_text_content returns None."""

        class NoneTextMsg(FakeMsg):
            def get_text_content(self):
                return None

        msg = NoneTextMsg(id="n4", role="user", content="anything")
        result = classify_importance(msg)
        assert result == Importance.TRIVIAL


class TestTopicClusteringInterleavedHints:
    """Gap #5: Topic clustering with interleaved known/unknown hints.

    Verifies forward-fill, backward-fill, and the "general" fallback
    when known-topic messages are interleaved with hint-less messages.
    """

    def test_forward_fill_propagates_topic_to_following_none(self):
        """A message with a known topic should forward-fill the next
        message that has no topic hint."""
        msgs = [
            _msg("There's a bug in the system", msg_id="1"),  # debugging
            _msg("How are you?", msg_id="2"),  # no hint -> inherits debugging
        ]
        clusters = cluster_by_topic(msgs)
        # Both should end up in the same cluster due to forward fill
        assert len(clusters) == 1
        assert clusters[0].topic == "debugging"
        assert len(clusters[0].messages) == 2

    def test_backward_fill_for_leading_nones(self):
        """Leading messages with no hint should backward-fill from
        the first message that has a hint."""
        msgs = [
            _msg("How are you?", msg_id="1"),  # no hint
            _msg("Let me check the config", msg_id="2"),  # configuration
        ]
        clusters = cluster_by_topic(msgs)
        # Backward fill: msg 1 inherits "configuration" from msg 2
        assert len(clusters) == 1
        assert clusters[0].topic == "configuration"

    def test_interleaved_known_unknown_known(self):
        """Known -> unknown -> different known creates proper splits."""
        msgs = [
            _msg("Error: connection failed", msg_id="1"),  # debugging
            _msg("Let me think about this", msg_id="2"),  # no hint -> fwd fill = debugging
            _msg("Now let me deploy the fix", msg_id="3"),  # deployment
        ]
        clusters = cluster_by_topic(msgs)
        # msgs 1+2 should cluster as debugging, msg 3 as deployment
        assert len(clusters) == 2
        assert clusters[0].topic == "debugging"
        assert len(clusters[0].messages) == 2
        assert clusters[1].topic == "deployment"

    def test_all_none_hints_become_general(self):
        """When no message has any topic hint, all become 'general'."""
        msgs = [
            _msg("Hello there", msg_id="1"),
            _msg("Nice weather", msg_id="2"),
            _msg("Indeed it is", msg_id="3"),
        ]
        clusters = cluster_by_topic(msgs)
        assert len(clusters) == 1
        assert clusters[0].topic == "general"
        assert len(clusters[0].messages) == 3

    def test_tool_msgs_interleaved_with_text(self):
        """Tool messages with known topics interleaved with plain text."""
        msgs = [
            _tool_msg("read_file", msg_id="t1"),  # file-ops
            _msg("The file looks correct", msg_id="m1"),  # no hint -> fwd fill
            _tool_msg("browser_use", msg_id="t2"),  # web-research
            _msg("Found the answer", msg_id="m2"),  # no hint -> fwd fill
        ]
        clusters = cluster_by_topic(msgs)
        # t1 + m1 = file-ops, t2 + m2 = web-research
        assert len(clusters) == 2
        assert clusters[0].topic == "file-ops"
        assert len(clusters[0].messages) == 2
        assert clusters[1].topic == "web-research"
        assert len(clusters[1].messages) == 2


class TestTieredCompactionEdgeCases:
    """Additional tiered compaction edge cases."""

    def test_all_critical_messages_nothing_compacted(self):
        """Gap #2 partial: when every message is CRITICAL, nothing
        gets compacted regardless of cycle."""
        msgs = [
            _msg("I decided to use glm-5", msg_id="d1"),
            _msg("From now on, use staging", msg_id="d2"),
            _msg("Config changed: port set to 8088", msg_id="d3"),
        ]
        plan = plan_compaction(
            msgs, {"d1": 0, "d2": 0, "d3": 0}, current_cycle=100
        )
        assert len(plan.to_compact) == 0
        assert len(plan.to_preserve) == 3
        assert plan.stats["tier_L0"] == 3

    def test_mixed_l1_ages_partial_compaction(self):
        """L1 messages at different ages: only the old ones compact."""
        msgs = [
            _msg("Error: disk full", msg_id="e1"),  # HIGH -> L1
            _msg("Fixed the issue", msg_id="e2"),  # HIGH -> L1
        ]
        # e1 was first seen at cycle 0, e2 at cycle 2
        plan = plan_compaction(
            msgs, {"e1": 0, "e2": 2}, current_cycle=2
        )
        compact_ids = {m.id for m in plan.to_compact}
        preserve_ids = {m.id for m in plan.to_preserve}
        # e1: age=2, survival=2 -> compacted
        assert "e1" in compact_ids
        # e2: age=0, survival=2 -> preserved
        assert "e2" in preserve_ids
