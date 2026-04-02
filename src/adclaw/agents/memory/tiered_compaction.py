# -*- coding: utf-8 -*-
"""Tiered compaction planning — importance-aware message selection.

Messages are assigned to tiers based on importance, and each tier has
a survival cycle count that determines how many compaction triggers
a message survives before being compacted:

- L0 (CRITICAL): Never auto-compacted (survival=999).
- L1 (HIGH, MEDIUM): Survives 2 compaction cycles.
- L2 (LOW, TRIVIAL): Compacted on first trigger.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List

from agentscope.message import Msg

from .importance import Importance, classify_importance

logger = logging.getLogger(__name__)

# How many compaction cycles each tier survives before being compacted
TIER_SURVIVAL_CYCLES: Dict[str, int] = {
    "L0": 999,  # effectively never (manual /compact only)
    "L1": 2,  # survive 2 compaction triggers
    "L2": 0,  # compacted on first trigger
}

# Maps Importance levels to tier names
IMPORTANCE_TO_TIER: Dict[Importance, str] = {
    Importance.CRITICAL: "L0",
    Importance.HIGH: "L1",
    Importance.MEDIUM: "L1",
    Importance.LOW: "L2",
    Importance.TRIVIAL: "L2",
}


@dataclass
class CompactionPlan:
    """Result of planning which messages to compact."""

    to_compact: List[Msg] = field(default_factory=list)
    to_preserve: List[Msg] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)


def plan_compaction(
    messages: List[Msg],
    cycle_counts: Dict[str, int],
    current_cycle: int,
) -> CompactionPlan:
    """Decide which messages to compact based on importance tiers.

    Args:
        messages: Messages in the compactable window (excludes system
            prompt and keep_recent).
        cycle_counts: Dict mapping msg.id to the compaction cycle number
            when the message was first seen. Messages not in this dict
            are treated as newly arrived (current_cycle).
        current_cycle: The current compaction cycle number.

    Returns:
        CompactionPlan with messages split into compact vs preserve.
    """
    plan = CompactionPlan()
    tier_counts: Dict[str, int] = {"L0": 0, "L1": 0, "L2": 0}

    for msg in messages:
        importance = classify_importance(msg)
        tier = IMPORTANCE_TO_TIER[importance]
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        survival = TIER_SURVIVAL_CYCLES[tier]

        first_seen = cycle_counts.get(msg.id, current_cycle)
        age_in_cycles = current_cycle - first_seen

        if age_in_cycles >= survival:
            plan.to_compact.append(msg)
        else:
            plan.to_preserve.append(msg)

    plan.stats = {
        "total": len(messages),
        "compacting": len(plan.to_compact),
        "preserving": len(plan.to_preserve),
        **{f"tier_{k}": v for k, v in tier_counts.items()},
    }

    logger.info(
        "Compaction plan: %d/%d messages to compact "
        "(L0=%d preserved, L1=%d, L2=%d), cycle=%d",
        len(plan.to_compact),
        len(messages),
        tier_counts["L0"],
        tier_counts["L1"],
        tier_counts["L2"],
        current_cycle,
    )

    return plan
