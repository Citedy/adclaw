# -*- coding: utf-8 -*-
"""Coordinator cron handler — integrates with the persona cron system."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from .models import PersonaOutcome, TaskStrategy
from .synthesis import run_synthesis_cycle
from ..persona_manager import PersonaManager
from ..tools.delegation_executor import DELEGATION_FAILED_PREFIX, execute_delegation

logger = logging.getLogger(__name__)


async def coordinator_cron_tick(
    persona_manager: PersonaManager,
    aom_manager,
    chat_model,
) -> str:
    """Execute one coordinator cron cycle.

    Called by the cron system when the coordinator's schedule fires.

    Returns:
        Human-readable summary of what the coordinator decided.
    """
    coordinator = persona_manager.get_coordinator()
    if coordinator is None:
        return "No coordinator persona configured."

    # Load active strategy from AOM
    active_strategy = await _load_active_strategy(aom_manager)

    # Run synthesis
    strategy = await run_synthesis_cycle(
        aom_manager=aom_manager,
        persona_manager=persona_manager,
        chat_model=chat_model,
        active_strategy=active_strategy,
    )

    # Check for abandonment
    if strategy.should_abandon():
        strategy.status = "abandoned"
        logger.warning(
            "Strategy '%s' abandoned after %d pivots",
            strategy.id,
            strategy.pivot_count,
        )
        await aom_manager.ingest_agent.ingest(
            content=strategy.model_dump_json(),
            source_type="manual",
            source_id=strategy.id,
            metadata={"coordinator_strategy": True, "strategy_id": strategy.id},
        )
        return f"Strategy abandoned: {strategy.goal} (too many pivots)"

    # Execute next steps, tracking which ones were actually executed
    results = []
    executed_indices: set[int] = set()
    for idx, step in enumerate(strategy.next_steps):
        persona = persona_manager.get_persona(step.persona_id)
        if persona is None:
            logger.warning("Unknown persona '%s' in next_steps", step.persona_id)
            executed_indices.add(idx)  # remove invalid steps
            continue

        if step.depends_on:
            # Check if dependency is met
            dep_outcomes = [
                o
                for o in strategy.outcomes
                if o.persona_id == step.depends_on and o.status == "success"
            ]
            if not dep_outcomes:
                logger.debug(
                    "Skipping step for %s — waiting on %s",
                    step.persona_id,
                    step.depends_on,
                )
                continue  # NOT marked as executed — preserve for next cycle

        executed_indices.add(idx)

        logger.info(
            "Coordinator delegating to @%s: %s",
            step.persona_id,
            step.task[:120],
        )
        # execute_delegation is sync — run in executor to avoid blocking
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, execute_delegation, persona, step.task, persona_manager
        )

        outcome_status = (
            "failed" if result.startswith(DELEGATION_FAILED_PREFIX) else "success"
        )
        strategy.add_outcome(
            PersonaOutcome(
                persona_id=step.persona_id,
                task_given=step.task,
                status=outcome_status,
                key_findings=[result[:500]],
            )
        )
        # Track pivots: if persona is stuck, increment pivot_count
        if outcome_status == "failed" and strategy.should_pivot(step.persona_id):
            strategy.pivot_count += 1
            logger.info(
                "Pivot #%d: persona @%s stuck",
                strategy.pivot_count,
                step.persona_id,
            )
        results.append(f"@{step.persona_id}: {outcome_status}")

    # Remove executed/invalid steps; preserve deferred steps with unmet depends_on
    strategy.next_steps = [
        s for idx, s in enumerate(strategy.next_steps) if idx not in executed_indices
    ]

    # Persist updated strategy
    await aom_manager.ingest_agent.ingest(
        content=strategy.model_dump_json(),
        source_type="manual",
        source_id=strategy.id,
        metadata={"coordinator_strategy": True, "strategy_id": strategy.id},
    )

    summary = (
        f"Strategy: {strategy.goal}\n"
        f"Synthesis: {strategy.synthesis[:300]}\n"
        f"Delegations: {'; '.join(results) if results else 'none (waiting)'}"
    )
    return summary


async def _load_active_strategy(aom_manager) -> Optional[TaskStrategy]:
    """Load the most recent active strategy from AOM.

    Iterates all citations and returns the active strategy with the
    latest updated_at timestamp, not just the first one found.
    """
    try:
        result = await aom_manager.query_agent.query(
            "coordinator strategy active",
            skip_synthesis=True,
        )
        candidates: list[TaskStrategy] = []
        for citation in result.citations:
            mem = citation.memory
            if mem.metadata.get("coordinator_strategy"):
                try:
                    data = json.loads(mem.content)
                    strategy = TaskStrategy(**data)
                    if strategy.status == "active":
                        candidates.append(strategy)
                except (json.JSONDecodeError, ValueError):
                    continue
        if candidates:
            # Return the newest strategy by updated_at timestamp
            return max(candidates, key=lambda s: s.updated_at)
    except Exception as exc:
        logger.warning("Failed to load active strategy: %s", exc)
    return None
