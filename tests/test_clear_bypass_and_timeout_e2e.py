# -*- coding: utf-8 -*-
"""E2E tests for /clear bypass and LLM timeout features.

Tests the actual ChannelManager class with mock channels to verify:
1. force_clear_session cancels in-progress tasks
2. force_clear_session deletes session files
3. LLM timeout fires and cleans up
4. Normal processing still works (no regression)
5. Telegram /clear calls force_clear on the manager
"""
import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any, AsyncIterator, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adclaw.app.channels.manager import ChannelManager, _process_batch
from adclaw.app.channels.base import BaseChannel, ProcessHandler


# ---------------------------------------------------------------------------
# Helpers / Mocks
# ---------------------------------------------------------------------------

class MockChannel(BaseChannel):
    """Minimal concrete channel for testing."""

    channel = "mock"
    uses_manager_queue = True

    def __init__(self, process: ProcessHandler, slow_seconds: float = 0.0):
        super().__init__(process)
        self.slow_seconds = slow_seconds
        self._started = False
        self._stopped = False
        self.processed_payloads: List[Any] = []
        self.system_messages: List[tuple] = []

    @classmethod
    def from_env(cls, process, **kw):
        return cls(process)

    @classmethod
    def from_config(cls, process, config, **kw):
        return cls(process)

    async def start(self):
        self._started = True

    async def stop(self):
        self._stopped = True

    def get_debounce_key(self, payload: Any) -> str:
        if isinstance(payload, dict):
            return payload.get("session_id", "default")
        return "default"

    def _is_native_payload(self, payload: Any) -> bool:
        return isinstance(payload, dict) and "content_parts" in payload

    async def _consume_one_request(self, payload: Any) -> None:
        """Simulate processing - optionally slow."""
        self.processed_payloads.append(payload)
        if self.slow_seconds > 0:
            await asyncio.sleep(self.slow_seconds)

    async def consume_one(self, payload: Any) -> None:
        await self._consume_one_request(payload)

    async def send_system_message(self, to: str, text: str) -> None:
        self.system_messages.append((to, text))

    async def send_content_parts(self, to, parts, meta):
        pass

    def to_handle_from_target(self, user_id, session_id):
        return user_id


async def _dummy_process(request: Any) -> AsyncIterator:
    yield  # pragma: no cover


# ---------------------------------------------------------------------------
# Scenario 1: force_clear_session cancels in-progress task
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_force_clear_cancels_in_progress_task():
    """Start a slow processing task, call force_clear_session while it's
    processing, verify task was cancelled and state cleaned up."""
    ch = MockChannel(_dummy_process, slow_seconds=60.0)
    mgr = ChannelManager([ch])

    await mgr.start_all()
    try:
        # Enqueue a payload that will take 60s to process
        payload = {"content_parts": [{"type": "text", "text": "hello"}],
                   "session_id": "sess1"}
        mgr._enqueue_one("mock", payload)

        # Also enqueue a pending message for the same key
        # (will be queued once first is picked up and in_progress is set)
        await asyncio.sleep(0.3)  # let consumer pick up first payload

        # Verify it's in progress
        assert ("mock", "sess1") in mgr._in_progress, \
            "Session should be in_progress"

        # Enqueue another payload that should go to pending
        payload2 = {"content_parts": [{"type": "text", "text": "world"}],
                    "session_id": "sess1"}
        mgr._enqueue_one("mock", payload2)
        assert ("mock", "sess1") in mgr._pending, \
            "Second payload should be in pending"

        # Now force clear
        was_active = await mgr.force_clear_session("mock", "sess1")

        assert was_active is True, "Should report task was active"
        assert ("mock", "sess1") not in mgr._in_progress, \
            "in_progress should be cleared"
        assert ("mock", "sess1") not in mgr._pending, \
            "pending should be cleared"
        assert ("mock", "sess1") not in mgr._processing_tasks, \
            "processing_tasks should be cleared"
    finally:
        await mgr.stop_all()

    print("PASS: Scenario 1 - force_clear_session cancels in-progress task")


# ---------------------------------------------------------------------------
# Scenario 2: force_clear_session deletes session files
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_force_clear_deletes_session_files():
    """Create temp dir with session files, call _delete_session_files,
    verify files are deleted."""
    ch = MockChannel(_dummy_process)
    mgr = ChannelManager([ch])

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create session files matching a key pattern
        key = "chat123"
        files_to_delete = [
            f"session_chat123_2026-03-15.json",
            f"backup_chat123.json",
        ]
        files_to_keep = [
            "session_other456.json",
            "unrelated.txt",
        ]
        for f in files_to_delete + files_to_keep:
            Path(tmpdir, f).write_text("{}")

        mgr.set_session_dir(tmpdir)
        mgr._delete_session_files(key)

        remaining = set(os.listdir(tmpdir))
        for f in files_to_delete:
            assert f not in remaining, f"File {f} should have been deleted"
        for f in files_to_keep:
            assert f in remaining, f"File {f} should have been kept"

    print("PASS: Scenario 2 - force_clear_session deletes session files")


# ---------------------------------------------------------------------------
# Scenario 3: LLM timeout fires and cleans up
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_timeout_fires_and_cleans_up():
    """Set _processing_timeout to 2s, start a 30s task, verify timeout."""
    ch = MockChannel(_dummy_process, slow_seconds=30.0)
    mgr = ChannelManager([ch])
    mgr._processing_timeout = 2.0

    await mgr.start_all()
    try:
        payload = {"content_parts": [{"type": "text", "text": "slow"}],
                   "session_id": "sess_timeout",
                   "meta": {"chat_id": "chat42"}}
        mgr._enqueue_one("mock", payload)

        # Wait for timeout to fire (2s) + some buffer
        await asyncio.sleep(3.5)

        # After timeout, state should be cleaned up
        assert ("mock", "sess_timeout") not in mgr._in_progress, \
            "in_progress should be cleared after timeout"
        assert ("mock", "sess_timeout") not in mgr._processing_tasks, \
            "processing_tasks should be cleared after timeout"

        # Channel should have received a timeout notification
        assert len(ch.system_messages) >= 1, \
            "Should have sent timeout notification"
        assert "timed out" in ch.system_messages[0][1].lower(), \
            "Timeout message should mention 'timed out'"
    finally:
        await mgr.stop_all()

    print("PASS: Scenario 3 - LLM timeout fires and cleans up")


# ---------------------------------------------------------------------------
# Scenario 4: Normal processing still works (no regression)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_normal_processing_completes():
    """Process a fast batch and verify it completes normally."""
    ch = MockChannel(_dummy_process, slow_seconds=0.1)
    mgr = ChannelManager([ch])
    mgr._processing_timeout = 60.0  # generous timeout

    await mgr.start_all()
    try:
        payload = {"content_parts": [{"type": "text", "text": "fast"}],
                   "session_id": "sess_fast"}
        mgr._enqueue_one("mock", payload)

        # Wait for processing to complete
        await asyncio.sleep(0.5)

        # Payload should have been processed
        assert len(ch.processed_payloads) == 1, \
            f"Expected 1 processed payload, got {len(ch.processed_payloads)}"
        assert ch.processed_payloads[0]["session_id"] == "sess_fast"

        # State should be clean
        assert ("mock", "sess_fast") not in mgr._in_progress, \
            "in_progress should be cleared after normal completion"
        assert ("mock", "sess_fast") not in mgr._processing_tasks, \
            "processing_tasks should be cleared after normal completion"

        # Pending should be flushed (empty)
        assert ("mock", "sess_fast") not in mgr._pending, \
            "pending should be empty after normal completion"
    finally:
        await mgr.stop_all()

    print("PASS: Scenario 4 - Normal processing completes correctly")


# ---------------------------------------------------------------------------
# Scenario 5: /clear in Telegram channel calls force_clear
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telegram_clear_calls_force_clear():
    """Verify TelegramChannel._force_clear_session calls
    manager.force_clear_session with correct args."""
    # We mock the TelegramChannel minimally to test the wiring
    from adclaw.app.channels.telegram.channel import TelegramChannel

    # Create a mock manager
    mock_manager = AsyncMock()
    mock_manager.force_clear_session = AsyncMock(return_value=True)

    # Create a mock bot
    mock_bot = AsyncMock()

    # Create a mock application with bot
    mock_app = MagicMock()
    mock_app.bot = mock_bot

    # Instantiate TelegramChannel with mocks
    tg = TelegramChannel.__new__(TelegramChannel)
    tg._channel_manager = mock_manager
    tg._application = mock_app
    tg.channel = "telegram"

    # Call _force_clear_session
    await tg._force_clear_session("12345")

    # Verify manager was called
    mock_manager.force_clear_session.assert_called_once_with("telegram", "12345")

    # Verify bot sent a message
    mock_bot.send_message.assert_called_once()
    call_kwargs = mock_bot.send_message.call_args
    assert call_kwargs.kwargs.get("chat_id") == "12345" or \
           (call_kwargs.args and call_kwargs.args[0] == "12345") or \
           call_kwargs[1].get("chat_id") == "12345", \
        "Bot should send message to the correct chat_id"

    print("PASS: Scenario 5 - Telegram /clear calls force_clear on manager")
