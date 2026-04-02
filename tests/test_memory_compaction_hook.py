# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from adclaw.agents.hooks.memory_compaction import MemoryCompactionHook


@dataclass
class FakeMsg:
    id: str
    role: str
    token_count: int
    content: str = "x"


class FakeMemory:
    def __init__(
        self,
        messages: list[FakeMsg],
        compressed_summary: str = "",
    ) -> None:
        self._messages = messages
        self._compressed_summary = compressed_summary
        self.updated_summary = None
        self.marked_ids: list[str] = []

    async def get_memory(
        self,
        exclude_mark: str | None = None,
        prepend_summary: bool = False,
        **_kwargs,
    ) -> list[FakeMsg]:
        del exclude_mark, prepend_summary
        return self._messages

    def get_compressed_summary(self) -> str:
        return self._compressed_summary

    async def update_compressed_summary(self, summary: str) -> None:
        self.updated_summary = summary
        self._compressed_summary = summary

    async def update_messages_mark(
        self,
        new_mark: str,
        msg_ids: list[str],
    ) -> int:
        del new_mark
        self.marked_ids = list(msg_ids)
        return len(msg_ids)


class FakeMemoryManager:
    def __init__(self) -> None:
        self.summary_task_messages: list[list[FakeMsg]] = []
        self.compact_calls: list[dict[str, Any]] = []

    def add_async_summary_task(self, messages: list[FakeMsg]) -> None:
        self.summary_task_messages.append(list(messages))

    async def compact_memory(
        self,
        messages: list[FakeMsg] | None = None,
        messages_to_summarize: list[FakeMsg] | None = None,
        previous_summary: str = "",
    ) -> str:
        msgs = messages if messages is not None else messages_to_summarize
        self.compact_calls.append(
            {
                "messages": list(msgs) if msgs else [],
                "previous_summary": previous_summary,
            },
        )
        return "compacted-summary"


class FakeFormatter:
    def __init__(self) -> None:
        self.calls = 0

    async def format(self, msgs: list[FakeMsg]) -> list[dict[str, Any]]:
        self.calls += 1
        return [
            {
                "role": msg.role,
                "content": str(getattr(msg, "content", "")),
                "_test_token_count": int(
                    getattr(msg, "token_count", 0)
                    or max(len(str(getattr(msg, "content", ""))) // 4, 1),
                ),
            }
            for msg in msgs
        ]


def _make_agent(messages: list[FakeMsg], summary: str = "") -> Any:
    memory = FakeMemory(messages=messages, compressed_summary=summary)
    formatter = FakeFormatter()
    return SimpleNamespace(
        memory=memory,
        formatter=formatter,
    )


async def _fake_safe_count_message_tokens(
    messages: list[dict[str, Any]],
) -> int:
    return sum(int(msg.get("_test_token_count", 0)) for msg in messages)


def _fake_safe_count_str_tokens(text: str) -> int:
    return len(text) // 4 if text else 0


async def test_compaction_triggers_on_total_context_budget(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "adclaw.agents.hooks.memory_compaction.safe_count_message_tokens",
        _fake_safe_count_message_tokens,
    )
    monkeypatch.setattr(
        "adclaw.agents.hooks.memory_compaction.safe_count_str_tokens",
        _fake_safe_count_str_tokens,
    )

    memory_manager = FakeMemoryManager()
    hook = MemoryCompactionHook(
        memory_manager=memory_manager,
        memory_compact_threshold=950,
        keep_recent=1,
    )

    # message_tokens = 950 (at threshold),
    # so no compaction by message-only count
    # summary_tokens > 0 for non-empty wrapped summary
    # total = message_tokens + summary_tokens > threshold => should compact.
    messages = [
        FakeMsg(id="sys", role="system", token_count=250),
        FakeMsg(id="old-1", role="user", token_count=250),
        FakeMsg(id="old-2", role="assistant", token_count=250),
        FakeMsg(id="recent", role="user", token_count=200),
    ]
    agent = _make_agent(messages=messages, summary="existing-summary")

    await hook(agent=agent, kwargs={})

    assert memory_manager.compact_calls
    assert memory_manager.summary_task_messages
    assert agent.memory.updated_summary == "compacted-summary"
    # With tiered compaction, L2 (TRIVIAL/LOW) messages are compacted on
    # cycle 0. Both "old-1" and "old-2" have content "x" (< 5 chars) →
    # TRIVIAL → L2, compacted immediately.
    assert "old-1" in agent.memory.marked_ids
    assert "old-2" in agent.memory.marked_ids
    assert agent.formatter.calls == 1


async def test_compaction_not_triggered_when_total_under_threshold(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "adclaw.agents.hooks.memory_compaction.safe_count_message_tokens",
        _fake_safe_count_message_tokens,
    )
    monkeypatch.setattr(
        "adclaw.agents.hooks.memory_compaction.safe_count_str_tokens",
        _fake_safe_count_str_tokens,
    )

    memory_manager = FakeMemoryManager()
    hook = MemoryCompactionHook(
        memory_manager=memory_manager,
        memory_compact_threshold=1000,
        keep_recent=1,
    )

    # message_tokens = 800
    # summary_tokens ~= wrapped-summary-length//4
    # total stays below threshold => should not compact.
    messages = [
        FakeMsg(id="sys", role="system", token_count=200),
        FakeMsg(id="old-1", role="user", token_count=200),
        FakeMsg(id="old-2", role="assistant", token_count=200),
        FakeMsg(id="recent", role="user", token_count=200),
    ]
    agent = _make_agent(messages=messages, summary="existing-summary")

    await hook(agent=agent, kwargs={})

    assert not memory_manager.compact_calls
    assert not memory_manager.summary_task_messages
    assert agent.memory.updated_summary is None
    assert agent.memory.marked_ids == []
    assert agent.formatter.calls == 1


# ===================================================================
# Gap #1: Multi-cycle hook integration test
# ===================================================================


async def test_multi_cycle_l1_survives_then_compacts(
    monkeypatch,
) -> None:
    """Verify _cycle_counts and _compaction_cycle state carries across
    multiple __call__ invocations. L1 (HIGH) messages should survive
    2 cycles then get compacted on the 3rd trigger.

    Criticality: 9/10 — if cycle state is lost between calls, L1
    messages either never compact (memory leak) or compact too early
    (losing important error context).
    """
    monkeypatch.setattr(
        "adclaw.agents.hooks.memory_compaction.safe_count_message_tokens",
        _fake_safe_count_message_tokens,
    )
    monkeypatch.setattr(
        "adclaw.agents.hooks.memory_compaction.safe_count_str_tokens",
        _fake_safe_count_str_tokens,
    )

    memory_manager = FakeMemoryManager()
    hook = MemoryCompactionHook(
        memory_manager=memory_manager,
        memory_compact_threshold=50,  # low threshold to always trigger
        keep_recent=1,
    )

    # HIGH message (L1, survival=2) + TRIVIAL message (L2, survival=0)
    # Content "x" is <5 chars -> TRIVIAL. "Error: disk full" -> HIGH.
    error_msg = FakeMsg(
        id="err1", role="user", token_count=100,
        content="Error: disk full",
    )
    trivial_msg = FakeMsg(
        id="triv1", role="assistant", token_count=100,
        content="x",
    )
    recent_msg = FakeMsg(
        id="recent", role="user", token_count=10,
        content="latest",
    )
    sys_msg = FakeMsg(
        id="sys", role="system", token_count=10,
        content="system prompt",
    )

    # --- Cycle 0 ---
    # Both error_msg and trivial_msg are compactable.
    # trivial_msg is L2 (age=0 >= survival=0) -> compacted.
    # error_msg is L1 (age=0 < survival=2) -> preserved.
    agent = _make_agent(
        messages=[sys_msg, error_msg, trivial_msg, recent_msg],
    )
    await hook(agent=agent, kwargs={})

    assert hook._compaction_cycle == 1
    assert "err1" in hook._cycle_counts  # still tracked
    # trivial_msg was compacted, error_msg was preserved by tiered plan,
    # but only to_compact messages go to summarization
    compact_call_0 = memory_manager.compact_calls[0]
    compacted_ids_0 = {m.id for m in compact_call_0["messages"]}
    assert "triv1" in compacted_ids_0
    assert "err1" not in compacted_ids_0

    # --- Cycle 1 ---
    # error_msg reappears (wasn't compacted). New trivial appears.
    memory_manager.compact_calls.clear()
    memory_manager.summary_task_messages.clear()
    trivial_msg2 = FakeMsg(
        id="triv2", role="assistant", token_count=100,
        content="y",
    )
    agent = _make_agent(
        messages=[sys_msg, error_msg, trivial_msg2, recent_msg],
    )
    await hook(agent=agent, kwargs={})

    assert hook._compaction_cycle == 2
    # error_msg: first_seen=0, age=1 < survival=2 -> still preserved
    compact_call_1 = memory_manager.compact_calls[0]
    compacted_ids_1 = {m.id for m in compact_call_1["messages"]}
    assert "err1" not in compacted_ids_1
    assert "triv2" in compacted_ids_1

    # --- Cycle 2 ---
    # error_msg: first_seen=0, current_cycle=2, age=2 >= survival=2 -> COMPACTED
    memory_manager.compact_calls.clear()
    memory_manager.summary_task_messages.clear()
    trivial_msg3 = FakeMsg(
        id="triv3", role="assistant", token_count=100,
        content="z",
    )
    agent = _make_agent(
        messages=[sys_msg, error_msg, trivial_msg3, recent_msg],
    )
    await hook(agent=agent, kwargs={})

    assert hook._compaction_cycle == 3
    compact_call_2 = memory_manager.compact_calls[0]
    compacted_ids_2 = {m.id for m in compact_call_2["messages"]}
    assert "err1" in compacted_ids_2  # finally compacted
    assert "triv3" in compacted_ids_2
    # err1 should be cleaned from cycle_counts after compaction
    assert "err1" not in hook._cycle_counts


# ===================================================================
# Gap #2: Early-return when all messages are L0/CRITICAL preserved
# ===================================================================


async def test_all_critical_messages_skip_summarization(
    monkeypatch,
) -> None:
    """When every compactable message is CRITICAL (L0), plan_compaction
    returns an empty to_compact list. The hook should skip LLM
    summarization, advance the cycle counter, and return None.

    Criticality: 8/10 — without this, all-critical windows would
    either trigger an empty LLM call (wasting tokens) or fail to
    advance the cycle (L1 messages would never age out).
    """
    monkeypatch.setattr(
        "adclaw.agents.hooks.memory_compaction.safe_count_message_tokens",
        _fake_safe_count_message_tokens,
    )
    monkeypatch.setattr(
        "adclaw.agents.hooks.memory_compaction.safe_count_str_tokens",
        _fake_safe_count_str_tokens,
    )

    memory_manager = FakeMemoryManager()
    hook = MemoryCompactionHook(
        memory_manager=memory_manager,
        memory_compact_threshold=50,
        keep_recent=1,
    )

    # All compactable messages are CRITICAL (decisions, system-level)
    messages = [
        FakeMsg(
            id="sys", role="system", token_count=10,
            content="system prompt",
        ),
        FakeMsg(
            id="d1", role="user", token_count=100,
            content="I decided to use glm-5 for production",
        ),
        FakeMsg(
            id="d2", role="user", token_count=100,
            content="From now on, deploy to staging first",
        ),
        FakeMsg(
            id="d3", role="user", token_count=100,
            content="Config changed: max_input_length set to 64000",
        ),
        FakeMsg(
            id="recent", role="user", token_count=10,
            content="latest question",
        ),
    ]
    agent = _make_agent(messages=messages)

    await hook(agent=agent, kwargs={})

    # No LLM summarization should have happened
    assert not memory_manager.compact_calls
    assert not memory_manager.summary_task_messages
    assert agent.memory.updated_summary is None
    assert agent.memory.marked_ids == []
    # But the cycle counter MUST advance so L1 messages age
    assert hook._compaction_cycle == 1


async def test_all_critical_cycle_advances_ages_l1_later(
    monkeypatch,
) -> None:
    """Extension of gap #2: after the all-critical early return advances
    the cycle, a subsequent call with L1 messages should see them
    with the correct age (accounting for the skipped cycle).

    Criticality: 8/10 — if the cycle doesn't advance on early-return,
    L1 messages introduced later will have an incorrect age.
    """
    monkeypatch.setattr(
        "adclaw.agents.hooks.memory_compaction.safe_count_message_tokens",
        _fake_safe_count_message_tokens,
    )
    monkeypatch.setattr(
        "adclaw.agents.hooks.memory_compaction.safe_count_str_tokens",
        _fake_safe_count_str_tokens,
    )

    memory_manager = FakeMemoryManager()
    hook = MemoryCompactionHook(
        memory_manager=memory_manager,
        memory_compact_threshold=50,
        keep_recent=1,
    )

    sys_msg = FakeMsg(
        id="sys", role="system", token_count=10, content="system prompt",
    )
    critical_msg = FakeMsg(
        id="d1", role="user", token_count=100,
        content="I decided to use glm-5",
    )
    recent = FakeMsg(id="recent", role="user", token_count=10, content="q")

    # Cycle 0: all critical -> early return, cycle advances to 1
    agent = _make_agent(messages=[sys_msg, critical_msg, recent])
    await hook(agent=agent, kwargs={})
    assert hook._compaction_cycle == 1

    # Cycle 1: introduce an L1 message. Its first_seen = cycle 1.
    error_msg = FakeMsg(
        id="err1", role="user", token_count=100,
        content="Error: connection refused",
    )
    agent = _make_agent(
        messages=[sys_msg, critical_msg, error_msg, recent],
    )
    await hook(agent=agent, kwargs={})

    # err1 first_seen should be 1 (not 0)
    assert hook._cycle_counts.get("err1") == 1


# ===================================================================
# Gap #3: Orphaned tool pairs fallback to compact all
# ===================================================================


async def test_orphaned_tool_pairs_fallback_to_compact_all(
    monkeypatch,
) -> None:
    """When tiered compaction splits messages such that preserved
    messages have orphaned tool_use without matching tool_result,
    the hook should detect invalid preserved messages and fall back
    to compacting ALL compactable messages.

    Criticality: 9/10 — orphaned tool pairs cause API errors with
    Claude/Anthropic (tool_result without tool_use). This is a
    data-corruption-level bug if not handled.

    Scenario: Both tool_use and tool_result are MEDIUM (L1, survival=2).
    The tool_result was first seen 2 cycles ago (aged out), while the
    tool_use was first seen 1 cycle ago (still preserved). This creates
    an orphan: tool_use preserved without its matching tool_result.
    """
    monkeypatch.setattr(
        "adclaw.agents.hooks.memory_compaction.safe_count_message_tokens",
        _fake_safe_count_message_tokens,
    )
    monkeypatch.setattr(
        "adclaw.agents.hooks.memory_compaction.safe_count_str_tokens",
        _fake_safe_count_str_tokens,
    )

    memory_manager = FakeMemoryManager()
    hook = MemoryCompactionHook(
        memory_manager=memory_manager,
        memory_compact_threshold=50,
        keep_recent=1,
    )

    sys_msg = FakeMsg(
        id="sys", role="system", token_count=10,
        content="system prompt",
    )

    # tool_use message: has tool blocks -> MEDIUM -> L1 (survival=2)
    tool_use_msg = FakeMsg(
        id="tu1", role="assistant", token_count=100,
        content=[
            {"type": "tool_use", "id": "call_123", "name": "execute_shell_command", "input": {}},
        ],
    )
    # tool_result message: has tool blocks -> MEDIUM -> L1 (survival=2)
    tool_result_msg = FakeMsg(
        id="tr1", role="user", token_count=100,
        content=[
            {"type": "tool_result", "id": "call_123", "content": "ok"},
        ],
    )
    recent = FakeMsg(
        id="recent", role="user", token_count=10,
        content="latest",
    )

    # Pre-seed cycle_counts to create age difference:
    # tool_result first seen at cycle 0, tool_use at cycle 1.
    # At current_cycle=2: tool_result age=2 >= survival=2 -> compacted,
    # tool_use age=1 < survival=2 -> preserved. Orphan!
    hook._cycle_counts = {"tr1": 0, "tu1": 1}
    hook._compaction_cycle = 2

    agent = _make_agent(
        messages=[sys_msg, tool_use_msg, tool_result_msg, recent],
    )
    await hook(agent=agent, kwargs={})

    # The hook should have detected the orphaned tool pair and
    # fallen back to compacting ALL messages (both tu1 and tr1)
    assert memory_manager.compact_calls
    compact_ids = {m.id for m in memory_manager.compact_calls[0]["messages"]}
    # Both messages should be compacted (fallback to all)
    assert "tu1" in compact_ids
    assert "tr1" in compact_ids


# ===================================================================
# Gap: Cycle counts pruned for messages no longer in compactable window
# ===================================================================


async def test_cycle_counts_pruned_for_disappeared_messages(
    monkeypatch,
) -> None:
    """When a message leaves the compactable window (e.g., it moved
    into keep_recent or was removed), its entry in _cycle_counts
    should be pruned to prevent unbounded memory growth.

    Criticality: 6/10 — memory leak in long-running sessions.
    """
    monkeypatch.setattr(
        "adclaw.agents.hooks.memory_compaction.safe_count_message_tokens",
        _fake_safe_count_message_tokens,
    )
    monkeypatch.setattr(
        "adclaw.agents.hooks.memory_compaction.safe_count_str_tokens",
        _fake_safe_count_str_tokens,
    )

    memory_manager = FakeMemoryManager()
    hook = MemoryCompactionHook(
        memory_manager=memory_manager,
        memory_compact_threshold=50,
        keep_recent=1,
    )

    sys_msg = FakeMsg(
        id="sys", role="system", token_count=10, content="system prompt",
    )
    recent = FakeMsg(id="recent", role="user", token_count=10, content="q")

    # Cycle 0: msg_a and msg_b in compactable window
    msg_a = FakeMsg(
        id="a", role="user", token_count=100,
        content="Error: problem A",  # HIGH -> L1
    )
    msg_b = FakeMsg(
        id="b", role="user", token_count=100,
        content="Error: problem B",  # HIGH -> L1
    )
    agent = _make_agent(messages=[sys_msg, msg_a, msg_b, recent])
    await hook(agent=agent, kwargs={})

    # Both should be tracked (L1, not yet compacted)
    assert "a" in hook._cycle_counts
    assert "b" in hook._cycle_counts

    # Cycle 1: msg_a disappears from compactable window (e.g., user
    # scrolled it into recent or it was externally removed).
    # Only msg_b remains.
    memory_manager.compact_calls.clear()
    memory_manager.summary_task_messages.clear()
    agent = _make_agent(messages=[sys_msg, msg_b, recent])
    await hook(agent=agent, kwargs={})

    # msg_a should be pruned from _cycle_counts
    assert "a" not in hook._cycle_counts
    # msg_b should still be tracked
    assert "b" in hook._cycle_counts
