# -*- coding: utf-8 -*-
"""ConsolidationEngine — finds patterns across memories and generates insights.

Upgraded with gate logic, 4-phase consolidation, and contradiction detection
per the AutoDream pattern (docs/architect-v2/1a-aom-consolidation-upgrade.md).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

from .embeddings import EmbeddingPipeline
from .models import AOMConfig, Consolidation, Memory
from .store import MemoryStore

logger = logging.getLogger(__name__)

_CONSOLIDATE_PROMPT = """You are analyzing a cluster of related memory entries.
Generate a concise insight that synthesizes the key information from these memories.

Memories:
{memories}

Write a single concise insight paragraph (2-4 sentences) that captures the most important information, patterns, or connections across these memories. Rate its importance 0.0-1.0.

Format your response as:
INSIGHT: <your insight>
IMPORTANCE: <float>"""

_CONTRADICTION_PROMPT = """Two memories about the same topic appear to contradict each other.

Memory A (created {a_date}):
{a_content}

Memory B (created {b_date}):
{b_content}

Which memory is more likely to be current and correct? Answer with exactly "A" or "B", then a brief reason.

Format:
WINNER: A or B
REASON: <one sentence>"""

# ---------------------------------------------------------------------------
# Cheap sentiment keywords for contradiction detection (Tier 1)
# ---------------------------------------------------------------------------
_POSITIVE_KEYWORDS = frozenset({
    "works", "correct", "confirmed", "enabled", "active", "fixed",
    "resolved", "success", "valid", "available", "supported", "true",
})
_NEGATIVE_KEYWORDS = frozenset({
    "broken", "wrong", "deprecated", "disabled", "inactive", "failed",
    "error", "invalid", "unavailable", "unsupported", "false", "removed",
})


class ConsolidationEngine:
    """Finds related memories, clusters them, and generates LLM insights.

    Upgraded with:
    - Gate logic (event -> time -> count) to skip empty cycles
    - 4-phase consolidation (orient -> gather -> consolidate -> prune)
    - Contradiction detection (cheap sentiment + LLM fallback)
    """

    def __init__(
        self,
        store: MemoryStore,
        embedder: EmbeddingPipeline,
        llm_caller: Callable[[str], Coroutine[Any, Any, str]],
        config: Optional[AOMConfig] = None,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.llm_caller = llm_caller
        self.config = config or AOMConfig()

        # Gate state
        self._new_memory_count: int = 0
        self._last_consolidation_ts: float = 0.0
        self._backoff_multiplier: float = 1.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def notify_new_memory(self) -> None:
        """Should be called by IngestAgent whenever a memory is inserted."""
        self._new_memory_count += 1

    def _should_run(self) -> bool:
        """Check gates in cheapest-first order. Returns True if cycle should run."""
        # Gate 1: Event gate (free — memory read)
        if self._new_memory_count == 0:
            logger.debug("Consolidation gate: no new memories, skipping")
            return False

        # Gate 2: Time gate (free — time comparison)
        now = time.monotonic()
        min_interval = self.config.consolidation_min_interval_seconds * self._backoff_multiplier
        if self._last_consolidation_ts > 0 and (now - self._last_consolidation_ts) < min_interval:
            logger.debug(
                "Consolidation gate: too soon (%.0fs < %.0fs), skipping",
                now - self._last_consolidation_ts,
                min_interval,
            )
            return False

        # Gate 3: Count gate (cheap — checks in-memory counter)
        if self._new_memory_count < self.config.consolidation_min_new_memories:
            logger.debug(
                "Consolidation gate: not enough new memories (%d < %d), skipping",
                self._new_memory_count,
                self.config.consolidation_min_new_memories,
            )
            return False

        return True

    async def run_consolidation_cycle(self) -> List[Consolidation]:
        """Run one 4-phase consolidation cycle."""

        # ---- Phase 1: Orient ----
        stats = await self.store.get_stats()
        total = stats.get("total_memories", 0)

        if total < 2:
            logger.debug("Orient: fewer than 2 total memories (%d), skipping", total)
            self._backoff_multiplier = min(self._backoff_multiplier * 2.0, 16.0)
            return []

        logger.info("Orient: total=%d", total)

        # ---- Phase 2: Gather ----
        working_set: List[Memory] = []

        # 2a: Unconsolidated memories
        fresh = await self.store.get_unconsolidated_memories(limit=50)
        working_set.extend(fresh)

        # 2b: Stale high-importance memories needing re-verification
        stale_days = self.config.stale_verification_days
        working_ids: Set[str] = {m.id for m in working_set}
        all_memories = await self.store.list_memories(limit=200, min_importance=0.7)
        for mem in all_memories:
            if mem.id in working_ids:
                continue
            if mem.is_deleted:
                continue
            if _is_stale(mem, stale_days):
                working_set.append(mem)
                working_ids.add(mem.id)

        if len(working_set) < 2:
            logger.debug("Gather: working set too small (%d), skipping", len(working_set))
            self._backoff_multiplier = min(self._backoff_multiplier * 2.0, 16.0)
            return []

        logger.info("Gather: %d fresh + stale memories in working set", len(working_set))

        # ---- Phase 3: Consolidate ----
        # 3a: Cluster by vector similarity
        clusters: List[List[str]] = []
        seen: set[str] = set()
        ws_by_id: Dict[str, Memory] = {m.id: m for m in working_set}

        for mem in working_set:
            if mem.id in seen:
                continue
            try:
                vec = await self.embedder.embed(mem.content)
                neighbors = await self.store.vector_search(vec, limit=5)
            except Exception as exc:
                logger.warning("Embedding/clustering failed for memory %s: %s", mem.id, exc)
                continue

            cluster_ids = [mem.id]
            for neighbor_id, _dist in neighbors:
                if neighbor_id != mem.id and neighbor_id not in seen:
                    neighbor = ws_by_id.get(neighbor_id)
                    # Don't cluster across different memory types
                    if neighbor and neighbor.memory_type != mem.memory_type:
                        continue
                    cluster_ids.append(neighbor_id)

            if len(cluster_ids) >= 2:
                clusters.append(cluster_ids)
                seen.update(cluster_ids)

        # 3b: Contradiction detection within each cluster
        if self.config.contradiction_detection_enabled:
            # Build lookup from working set to avoid re-fetching
            mem_by_id = {m.id: m for m in working_set}
            for cluster_ids in clusters:
                cluster_mems = [
                    mem_by_id[mid]
                    for mid in cluster_ids
                    if mid in mem_by_id and not mem_by_id[mid].is_deleted
                ]
                await self._detect_contradictions(cluster_mems)

        # 3c: Generate insights
        results: List[Consolidation] = []
        touched_ids: List[str] = []

        for cluster_ids in clusters:
            try:
                insight = await self._generate_insight(cluster_ids)
                if insight:
                    results.append(insight)
                    await self.store.mark_consolidated(cluster_ids)
                    touched_ids.extend(cluster_ids)
            except Exception as exc:
                logger.warning("Insight generation failed: %s", exc)

        # 3d: Mark all touched memories as verified
        if touched_ids:
            try:
                await self.store.mark_verified(touched_ids)
            except Exception as exc:
                logger.warning("mark_verified failed: %s", exc)

        logger.info("Consolidate: %d clusters -> %d insights", len(clusters), len(results))

        # ---- Phase 4: Prune ----
        try:
            prune_stats = await temporal_prune(self.store)
            if prune_stats["deleted"] > 0 or prune_stats["condensed"] > 0:
                logger.info(
                    "Temporal pruning: deleted=%d, condensed=%d, kept=%d",
                    prune_stats["deleted"],
                    prune_stats["condensed"],
                    prune_stats["kept"],
                )
        except Exception as exc:
            logger.warning("Temporal pruning failed: %s", exc)

        # Orphan cleanup
        try:
            orphans = await self.store.cleanup_orphan_consolidations()
            if orphans > 0:
                logger.info("Orphan consolidation cleanup: removed %d", orphans)
        except Exception as exc:
            logger.warning("Orphan cleanup failed: %s", exc)

        # ---- Post-cycle bookkeeping ----
        # Reset counter AFTER successful cycle (not before)
        self._new_memory_count = 0
        self._last_consolidation_ts = time.monotonic()

        # Reset backoff on productive cycle, increase on empty
        if results:
            self._backoff_multiplier = 1.0
        else:
            self._backoff_multiplier = min(self._backoff_multiplier * 2.0, 16.0)

        return results

    # ------------------------------------------------------------------
    # Contradiction detection
    # ------------------------------------------------------------------

    @staticmethod
    def _cheap_sentiment(text: str) -> Optional[bool]:
        """Keyword-based sentiment: True=positive, False=negative, None=neutral."""
        words = set(re.findall(r'\b\w+\b', text.lower()))
        pos = len(words & _POSITIVE_KEYWORDS)
        neg = len(words & _NEGATIVE_KEYWORDS)
        if pos > neg:
            return True
        if neg > pos:
            return False
        return None

    async def _detect_contradictions(self, memories: List[Memory]) -> None:
        """Find same-topic pairs with opposing sentiment and resolve them."""
        if len(memories) < 2:
            return

        for i in range(len(memories)):
            for j in range(i + 1, len(memories)):
                a, b = memories[i], memories[j]

                # Skip if either is already superseded
                if a.superseded_by or b.superseded_by:
                    continue

                # Check topic overlap
                shared_topics = set(a.topics) & set(b.topics)
                if not shared_topics:
                    continue

                # Tier 1: cheap sentiment check
                sent_a = self._cheap_sentiment(a.content)
                sent_b = self._cheap_sentiment(b.content)

                if sent_a is None or sent_b is None or sent_a == sent_b:
                    continue

                # Opposing sentiment on shared topic — resolve
                logger.info(
                    "Contradiction detected: %s vs %s on topics %s",
                    a.id[:8],
                    b.id[:8],
                    shared_topics,
                )
                await self._resolve_contradiction(a, b)

    async def _resolve_contradiction(self, a: Memory, b: Memory) -> None:
        """Use LLM to decide which memory wins; mark loser as superseded."""
        try:
            prompt = _CONTRADICTION_PROMPT.format(
                a_date=a.created_at,
                a_content=a.content[:500],
                b_date=b.created_at,
                b_content=b.content[:500],
            )
            raw = await self.llm_caller(prompt)

            # Check if LLM response contains a parseable WINNER line
            winner_label = None
            for line in raw.strip().split("\n"):
                if line.strip().upper().startswith("WINNER:"):
                    val = line.split(":", 1)[1].strip().upper()
                    if val.startswith("A"):
                        winner_label = "A"
                    elif val.startswith("B"):
                        winner_label = "B"
                    # else: unrecognized value, winner_label stays None
                    break

            if winner_label is None:
                # No WINNER line found — LLM response is unparseable, skip resolution
                logger.warning(
                    "Contradiction resolution skipped: LLM response unparseable for %s vs %s",
                    a.id[:8],
                    b.id[:8],
                )
                return

            if winner_label == "A":
                winner, loser = a, b
            else:
                winner, loser = b, a

            await self.store.mark_superseded(loser.id, winner.id)
            # Update in-memory object so subsequent iterations don't re-resolve
            loser.superseded_by = winner.id
            loser.is_deleted = 1
            logger.info(
                "Contradiction resolved: %s wins over %s",
                winner.id[:8],
                loser.id[:8],
            )
        except Exception as exc:
            logger.warning("Contradiction resolution failed: %s", exc)

    # ------------------------------------------------------------------
    # Insight generation
    # ------------------------------------------------------------------

    async def _generate_insight(self, memory_ids: List[str]) -> Optional[Consolidation]:
        """Generate an insight from a cluster of memory IDs."""
        memories_text = []
        for mid in memory_ids:
            mem = await self.store.get_memory(mid)
            if mem and not mem.is_deleted:
                memories_text.append(f"- [{mem.source_type}/{mem.source_id}] {mem.content[:500]}")

        if not memories_text:
            return None

        prompt = _CONSOLIDATE_PROMPT.format(memories="\n".join(memories_text))
        raw = await self.llm_caller(prompt)

        # Parse response
        insight_text = raw.strip()
        importance = 0.5
        for line in raw.strip().split("\n"):
            if line.startswith("INSIGHT:"):
                insight_text = line[len("INSIGHT:"):].strip()
            elif line.startswith("IMPORTANCE:"):
                try:
                    importance = float(line[len("IMPORTANCE:"):].strip())
                except ValueError:
                    pass

        consolidation = Consolidation(
            insight=insight_text,
            memory_ids=memory_ids,
            importance=importance,
        )
        return await self.store.insert_consolidation(consolidation)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_stale(mem: Memory, stale_days: int) -> bool:
    """Check if a memory's last_verified_at is older than stale_days."""
    ref = mem.last_verified_at or mem.created_at
    try:
        dt = datetime.fromisoformat(ref.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
        return age > stale_days
    except Exception:
        return False


# ---------------------------------------------------------------------------
# R4: Temporal Pruning
# ---------------------------------------------------------------------------

# Classification: green (ephemeral), yellow (useful), red (critical)
# Uses actual source_type Literal values from Memory model
_GREEN_TYPES = {"chat", "manual"}
_RED_TYPES = {"skill", "mcp_tool"}  # structured data worth preserving
_GREEN_MAX_DAYS = 7
_YELLOW_MAX_DAYS = 30


def _classify_memory_color(mem: Memory) -> str:
    """Classify memory into green/yellow/red by source_type and importance."""
    st = mem.source_type.lower()
    if mem.importance >= 0.8 or st in _RED_TYPES:
        return "red"
    if st in _GREEN_TYPES and mem.importance < 0.5:
        return "green"
    return "yellow"


def _memory_age_days(mem: Memory) -> float:
    """Calculate age in days from created_at string."""
    try:
        created = datetime.fromisoformat(mem.created_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - created).total_seconds() / 86400
    except Exception:
        return 0.0


async def temporal_prune(store: MemoryStore) -> Dict[str, int]:
    """Age-based pruning: delete old green, condense old yellow, keep red.

    Returns:
        Stats dict with counts: deleted, condensed, kept.
    """
    stats = {"deleted": 0, "condensed": 0, "kept": 0}
    memories = await store.list_memories(limit=500, min_importance=0.0)

    for mem in memories:
        color = _classify_memory_color(mem)
        age = _memory_age_days(mem)

        if color == "red":
            stats["kept"] += 1
            continue

        if color == "green" and age > _GREEN_MAX_DAYS:
            await store.delete_memory(mem.id, hard=False)
            stats["deleted"] += 1
        elif color == "yellow" and age > _YELLOW_MAX_DAYS:
            # Condense to first line only
            first_line = mem.content.split("\n")[0][:200]
            if len(first_line) < len(mem.content):
                await store.update_memory_content(mem.id, first_line)
                stats["condensed"] += 1
            else:
                stats["kept"] += 1
        else:
            stats["kept"] += 1

    return stats


class ConsolidationScheduler:
    """Runs consolidation cycles on a schedule."""

    def __init__(
        self,
        engine: ConsolidationEngine,
        interval_minutes: int = 60,
    ) -> None:
        self.engine = engine
        self.interval_minutes = interval_minutes
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the scheduler loop. Idempotent — safe to call multiple times."""
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())
        logger.info("Consolidation scheduler started (every %d min)", self.interval_minutes)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.interval_minutes * 60)
            try:
                if self.engine._should_run():
                    await self.engine.run_consolidation_cycle()
                else:
                    logger.debug("Scheduler: gates blocked, skipping cycle")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Consolidation cycle error: %s", exc)
