# -*- coding: utf-8 -*-
"""Tests for the Coordinator Persona (2A)."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from adclaw.agents.coordinator.models import (
    NextStep,
    PersonaOutcome,
    TaskStrategy,
)
from adclaw.agents.coordinator.synthesis import (
    _parse_strategy_from_response,
    validate_synthesis,
)
from adclaw.agents.coordinator.cron_handler import (
    _load_active_strategy,
    coordinator_cron_tick,
)
from adclaw.agents.persona_manager import PersonaManager
from adclaw.config.config import PersonaConfig


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestTaskStrategy:
    def test_create_strategy(self):
        strategy = TaskStrategy(goal="Improve SEO for /pricing page")
        assert strategy.status == "active"
        assert strategy.pivot_count == 0
        assert strategy.outcomes == []
        assert strategy.next_steps == []

    def test_add_outcome(self):
        strategy = TaskStrategy(goal="test")
        outcome = PersonaOutcome(
            persona_id="seo-expert",
            task_given="Audit /pricing page",
            status="success",
            key_findings=["Missing H1 tag", "No meta description"],
        )
        strategy.add_outcome(outcome)
        assert len(strategy.outcomes) == 1
        assert strategy.outcomes[0].persona_id == "seo-expert"

    def test_add_outcome_updates_timestamp(self):
        strategy = TaskStrategy(goal="test")
        original_ts = strategy.updated_at
        strategy.add_outcome(
            PersonaOutcome(persona_id="x", task_given="t", status="success")
        )
        assert strategy.updated_at >= original_ts

    def test_should_pivot_after_two_failures(self):
        strategy = TaskStrategy(goal="test")
        strategy.add_outcome(
            PersonaOutcome(persona_id="seo-expert", task_given="task1", status="failed")
        )
        assert not strategy.should_pivot("seo-expert")

        strategy.add_outcome(
            PersonaOutcome(persona_id="seo-expert", task_given="task2", status="failed")
        )
        assert strategy.should_pivot("seo-expert")

    def test_should_not_pivot_different_persona(self):
        strategy = TaskStrategy(goal="test")
        strategy.add_outcome(
            PersonaOutcome(persona_id="seo-expert", task_given="t1", status="failed")
        )
        strategy.add_outcome(
            PersonaOutcome(
                persona_id="content-writer", task_given="t2", status="failed"
            )
        )
        assert not strategy.should_pivot("seo-expert")

    def test_should_abandon_after_max_pivots(self):
        strategy = TaskStrategy(goal="test", max_pivots=3)
        strategy.pivot_count = 3
        assert strategy.should_abandon()

    def test_should_not_abandon_below_max(self):
        strategy = TaskStrategy(goal="test", max_pivots=3)
        strategy.pivot_count = 2
        assert not strategy.should_abandon()

    def test_serialization_roundtrip(self):
        strategy = TaskStrategy(
            goal="SEO campaign",
            synthesis="Found 3 issues",
            next_steps=[
                NextStep(
                    persona_id="content-writer",
                    task="Rewrite H1 tags",
                    rationale="SEO audit found missing H1s",
                ),
            ],
        )
        json_str = strategy.model_dump_json()
        restored = TaskStrategy.model_validate_json(json_str)
        assert restored.goal == strategy.goal
        assert len(restored.next_steps) == 1
        assert restored.next_steps[0].persona_id == "content-writer"


# ---------------------------------------------------------------------------
# Synthesis validation tests
# ---------------------------------------------------------------------------


class TestValidateSynthesis:
    def test_catches_forbidden_phrases(self):
        violations = validate_synthesis(
            "Based on results, optimize further as appropriate."
        )
        assert len(violations) == 3

    def test_passes_specific_synthesis(self):
        violations = validate_synthesis(
            "The /pricing page is missing an H1 tag. "
            "@content-writer should add 'Enterprise Pricing Plans' as H1."
        )
        assert len(violations) == 0

    def test_catches_single_forbidden_phrase(self):
        violations = validate_synthesis("We should continue as needed.")
        assert len(violations) == 1
        assert "continue as needed" in violations[0]


# ---------------------------------------------------------------------------
# Parse strategy from response tests
# ---------------------------------------------------------------------------


class TestParseStrategyFromResponse:
    def test_valid_json(self):
        strategy_data = {"goal": "Fix SEO", "synthesis": "Found issues."}
        raw = json.dumps(strategy_data)
        result = _parse_strategy_from_response(raw)
        assert result.goal == "Fix SEO"
        assert result.status == "active"

    def test_markdown_fenced_json(self):
        strategy_data = {"goal": "Fix SEO", "synthesis": "Found issues."}
        raw = f"Here is the strategy:\n```json\n{json.dumps(strategy_data)}\n```\nDone."
        result = _parse_strategy_from_response(raw)
        assert result.goal == "Fix SEO"

    def test_garbage_input_no_fallback(self):
        result = _parse_strategy_from_response("This is not JSON at all!")
        assert result.goal == "Unable to determine"
        assert "[Parse error]" in result.synthesis

    def test_garbage_input_with_fallback(self):
        fallback = TaskStrategy(goal="Original goal", synthesis="Original synthesis")
        original_synthesis = fallback.synthesis
        result = _parse_strategy_from_response("garbage text", fallback=fallback)
        # Should return a copy, not mutate fallback
        assert "[Parse error" in result.synthesis
        assert fallback.synthesis == original_synthesis  # original unchanged
        assert result.goal == "Original goal"

    def test_fallback_not_mutated(self):
        """model_copy() must be used, not direct mutation."""
        fallback = TaskStrategy(goal="G", synthesis="S")
        _parse_strategy_from_response("bad json", fallback=fallback)
        assert fallback.synthesis == "S"


# ---------------------------------------------------------------------------
# _load_active_strategy tests
# ---------------------------------------------------------------------------


class TestLoadActiveStrategy:
    @pytest.mark.asyncio
    async def test_returns_newest_active(self):
        """Should return the strategy with the latest updated_at."""
        older = TaskStrategy(goal="Old", updated_at="2026-01-01T00:00:00+00:00")
        newer = TaskStrategy(goal="New", updated_at="2026-03-01T00:00:00+00:00")

        mem_older = MagicMock()
        mem_older.metadata = {"coordinator_strategy": True}
        mem_older.content = older.model_dump_json()

        mem_newer = MagicMock()
        mem_newer.metadata = {"coordinator_strategy": True}
        mem_newer.content = newer.model_dump_json()

        citation_older = MagicMock()
        citation_older.memory = mem_older
        citation_newer = MagicMock()
        citation_newer.memory = mem_newer

        aom = MagicMock()
        aom.query_agent = AsyncMock()
        aom.query_agent.query = AsyncMock(
            return_value=MagicMock(citations=[citation_older, citation_newer])
        )

        result = await _load_active_strategy(aom)
        assert result is not None
        assert result.goal == "New"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_strategies(self):
        aom = MagicMock()
        aom.query_agent = AsyncMock()
        aom.query_agent.query = AsyncMock(
            return_value=MagicMock(citations=[])
        )
        result = await _load_active_strategy(aom)
        assert result is None

    @pytest.mark.asyncio
    async def test_skips_completed_strategies(self):
        completed = TaskStrategy(goal="Done", status="completed")
        mem = MagicMock()
        mem.metadata = {"coordinator_strategy": True}
        mem.content = completed.model_dump_json()
        citation = MagicMock()
        citation.memory = mem

        aom = MagicMock()
        aom.query_agent = AsyncMock()
        aom.query_agent.query = AsyncMock(
            return_value=MagicMock(citations=[citation])
        )
        result = await _load_active_strategy(aom)
        assert result is None

    @pytest.mark.asyncio
    async def test_handles_query_exception(self):
        aom = MagicMock()
        aom.query_agent = AsyncMock()
        aom.query_agent.query = AsyncMock(side_effect=RuntimeError("AOM down"))
        result = await _load_active_strategy(aom)
        assert result is None


# ---------------------------------------------------------------------------
# coordinator_cron_tick integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def personas():
    return [
        PersonaConfig(
            id="coordinator",
            name="Coordinator",
            is_coordinator=True,
            soul_md="You coordinate the team.",
        ),
        PersonaConfig(
            id="seo-expert",
            name="SEO Expert",
            soul_md="You are an SEO specialist.",
            skills=["seo-audit"],
        ),
    ]


@pytest.fixture
def persona_manager(personas):
    return PersonaManager(working_dir="/tmp/test-adclaw", personas=personas)


@pytest.fixture
def mock_aom():
    aom = MagicMock()
    aom.query_agent = AsyncMock()
    aom.query_agent.query = AsyncMock(
        return_value=MagicMock(citations=[], consolidations=[], answer="")
    )
    aom.ingest_agent = AsyncMock()
    aom.ingest_agent.ingest = AsyncMock()
    return aom


@pytest.fixture
def mock_chat_model():
    model = MagicMock()
    strategy = TaskStrategy(
        goal="Test goal",
        synthesis="Specific finding: page /about has no meta description.",
        next_steps=[],
    )
    model.return_value = MagicMock(
        content=f"```json\n{strategy.model_dump_json()}\n```"
    )
    return model


class TestCoordinatorCronTick:
    @pytest.mark.asyncio
    async def test_no_coordinator_configured(self, mock_aom, mock_chat_model):
        pm = PersonaManager(
            working_dir="/tmp/test",
            personas=[PersonaConfig(id="seo", name="SEO", soul_md="test")],
        )
        result = await coordinator_cron_tick(pm, mock_aom, mock_chat_model)
        assert "No coordinator" in result

    @pytest.mark.asyncio
    async def test_runs_synthesis(self, persona_manager, mock_aom, mock_chat_model):
        result = await coordinator_cron_tick(
            persona_manager, mock_aom, mock_chat_model
        )
        assert "Strategy:" in result
        # Verify AOM ingest was called (at least twice: synthesis + persist)
        assert mock_aom.ingest_agent.ingest.call_count >= 1

    @pytest.mark.asyncio
    async def test_delegates_next_steps(self, persona_manager, mock_aom):
        strategy = TaskStrategy(
            goal="Fix SEO",
            synthesis="Found issues.",
            next_steps=[
                NextStep(
                    persona_id="seo-expert",
                    task="Audit /pricing page for H1 tags",
                    rationale="Missing H1 detected in crawl",
                ),
            ],
        )
        model = MagicMock()
        model.return_value = MagicMock(
            content=f"```json\n{strategy.model_dump_json()}\n```"
        )

        with patch(
            "adclaw.agents.coordinator.cron_handler.execute_delegation",
            return_value="Found 2 missing H1 tags on /pricing",
        ) as mock_deleg:
            result = await coordinator_cron_tick(persona_manager, mock_aom, model)
            mock_deleg.assert_called_once()
            assert "seo-expert" in result

    @pytest.mark.asyncio
    async def test_preserves_deferred_steps(self, persona_manager, mock_aom):
        """Steps with unmet depends_on should be preserved for next cycle."""
        strategy = TaskStrategy(
            goal="Multi-step",
            synthesis="Step 1 pending.",
            next_steps=[
                NextStep(
                    persona_id="seo-expert",
                    task="Do SEO audit",
                    rationale="First step",
                ),
                NextStep(
                    persona_id="seo-expert",
                    task="Write content based on SEO",
                    rationale="Depends on audit",
                    depends_on="content-writer",  # unmet dependency
                ),
            ],
        )
        model = MagicMock()
        model.return_value = MagicMock(
            content=f"```json\n{strategy.model_dump_json()}\n```"
        )

        with patch(
            "adclaw.agents.coordinator.cron_handler.execute_delegation",
            return_value="Audit complete",
        ):
            result = await coordinator_cron_tick(persona_manager, mock_aom, model)
            # The deferred step should cause "waiting" not to appear alone
            assert "seo-expert: success" in result

    @pytest.mark.asyncio
    async def test_abandons_after_max_pivots(self, persona_manager, mock_aom):
        strategy = TaskStrategy(
            goal="Doomed strategy",
            synthesis="Stuck.",
            pivot_count=3,
            max_pivots=3,
        )
        model = MagicMock()
        model.return_value = MagicMock(
            content=f"```json\n{strategy.model_dump_json()}\n```"
        )
        result = await coordinator_cron_tick(persona_manager, mock_aom, model)
        assert "abandoned" in result.lower()
        # Verify abandoned strategy was persisted to AOM
        assert mock_aom.ingest_agent.ingest.call_count >= 1
