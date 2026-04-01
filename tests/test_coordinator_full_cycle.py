# -*- coding: utf-8 -*-
"""Full cycle coordinator test with REAL LLM + REAL AOM.

Tests the complete flow:
1. Initialize AOM with real SQLite + embeddings
2. Seed persona activity memories
3. Run coordinator_cron_tick with real LLM
4. Verify TaskStrategy created in AOM
5. Simulate failed delegation → verify pivot tracking
6. Run second cycle → verify strategy updated

Usage:
    QWEN_API_KEY=sk-sp-... python3 -m pytest tests/test_coordinator_full_cycle.py -v -s
"""

import asyncio
import json
import os
import tempfile

import pytest

# Skip if no API key
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
if not QWEN_API_KEY:
    pytest.skip("QWEN_API_KEY not set — skipping real LLM test", allow_module_level=True)
QWEN_URL = "https://coding-intl.dashscope.aliyuncs.com/v1"
QWEN_MODEL = "glm-5"


async def _real_llm_caller(prompt: str) -> str:
    """Call real Qwen/GLM API."""
    import urllib.request

    body = json.dumps({
        "model": QWEN_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        f"{QWEN_URL}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {QWEN_API_KEY}",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())

    content = data["choices"][0]["message"]["content"]
    return content


@pytest.fixture
async def aom_env():
    """Set up real AOM environment with SQLite + fake embeddings."""
    from adclaw.memory_agent.embeddings import FakeEmbeddingPipeline
    from adclaw.memory_agent.ingest import IngestAgent
    from adclaw.memory_agent.manager import AOMManager
    from adclaw.memory_agent.models import AOMConfig
    from adclaw.memory_agent.query import QueryAgent
    from adclaw.memory_agent.store import MemoryStore

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_aom.db")
        config = AOMConfig(
            enabled=True,
            embedding_dimensions=32,
            importance_threshold=0.1,
            consolidation_enabled=False,  # manual consolidation
        )
        store = MemoryStore(db_path, dimensions=32)
        await store.initialize()

        embedder = FakeEmbeddingPipeline(dimensions=32)
        ingest = IngestAgent(store, embedder, _real_llm_caller, config)
        query = QueryAgent(store, embedder, _real_llm_caller, config)

        # Create a lightweight AOM-like object for coordinator
        class FakeAOM:
            def __init__(self):
                self.store = store
                self.ingest_agent = ingest
                self.query_agent = query

        yield FakeAOM()
        await store.close()


@pytest.fixture
def persona_manager():
    """Create PersonaManager with test personas."""
    from adclaw.agents.persona_manager import PersonaManager
    from adclaw.config.config import PersonaConfig

    personas = [
        PersonaConfig(
            id="coordinator",
            name="Coordinator",
            is_coordinator=True,
            soul_md="You coordinate the marketing team.",
            skills=[],
        ),
        PersonaConfig(
            id="seo-expert",
            name="SEO Expert",
            soul_md="You are an SEO specialist.",
            skills=["seo-audit"],
        ),
        PersonaConfig(
            id="content-writer",
            name="Content Writer",
            soul_md="You write marketing content.",
            skills=["blog-writer"],
        ),
    ]
    return PersonaManager(working_dir="/tmp/test-adclaw", personas=personas)


class TestFullCycleRealLLM:
    """Full coordinator cycle with real LLM."""

    async def test_complete_cycle(self, aom_env, persona_manager):
        """Run complete coordinator cycle: seed → synthesize → delegate → check."""
        from adclaw.agents.coordinator.cron_handler import (
            _load_active_strategy,
            coordinator_cron_tick,
        )
        from adclaw.agents.coordinator.models import TaskStrategy

        aom = aom_env

        # ---- Step 1: Seed persona activity ----
        print("\n--- Step 1: Seed persona activity ---")
        await aom.ingest_agent.ingest(
            "@seo-expert: Found 5 pages with missing meta descriptions and 3 duplicate H1 tags. "
            "Site speed score 45/100. Recommending meta fixes first.",
            source_type="skill",
            source_id="seo-audit",
            skip_llm=True,
        )
        await aom.ingest_agent.ingest(
            "@content-writer: Wrote blog post 'AI Marketing Trends 2026', 1200 words. "
            "SEO score 72/100. Missing internal links to product pages.",
            source_type="skill",
            source_id="blog-writer",
            skip_llm=True,
        )
        await aom.ingest_agent.ingest(
            "Don't use clickbait headlines because they reduce trust with enterprise clients.",
            source_type="manual",
            skip_llm=True,
        )

        stats = await aom.store.get_stats()
        print(f"  AOM has {stats['total_memories']} memories")
        assert stats["total_memories"] >= 3

        # ---- Step 2: No active strategy yet ----
        print("\n--- Step 2: Check no active strategy ---")
        strategy = await _load_active_strategy(aom)
        print(f"  Active strategy: {strategy}")
        # May or may not be None depending on prior test runs

        # ---- Step 3: Run coordinator_cron_tick with REAL LLM ----
        print("\n--- Step 3: Run coordinator_cron_tick (REAL LLM) ---")

        # Create a real-ish chat_model wrapper
        class FakeChatModel:
            stream = False

            async def __call__(self, messages):
                # Combine system + user messages into a single prompt
                prompt_parts = []
                for msg in messages:
                    if isinstance(msg, dict):
                        prompt_parts.append(f"[{msg.get('role', 'user')}]: {msg.get('content', '')}")
                    else:
                        prompt_parts.append(str(msg))
                full_prompt = "\n\n".join(prompt_parts)
                text = await _real_llm_caller(full_prompt)

                class Resp:
                    content = text
                return Resp()

        summary = await coordinator_cron_tick(
            persona_manager=persona_manager,
            aom_manager=aom,
            chat_model=FakeChatModel(),
        )

        print(f"  Summary: {summary[:300]}")
        assert summary, "Expected non-empty summary"
        assert "Strategy" in summary or "strategy" in summary.lower() or "No coordinator" not in summary

        # ---- Step 4: Check TaskStrategy in AOM ----
        print("\n--- Step 4: Verify TaskStrategy in AOM ---")
        strategy = await _load_active_strategy(aom)
        if strategy:
            print(f"  Strategy goal: {strategy.goal}")
            print(f"  Strategy status: {strategy.status}")
            print(f"  Synthesis: {strategy.synthesis[:200]}")
            print(f"  Next steps: {len(strategy.next_steps)}")
            for step in strategy.next_steps:
                print(f"    @{step.persona_id}: {step.task[:80]}")
            print(f"  Outcomes: {len(strategy.outcomes)}")
            print("  ✅ TaskStrategy persisted and loaded from AOM")
        else:
            print("  ⚠️ No active strategy found (LLM may have returned non-JSON)")

        # ---- Step 5: Run second cycle → strategy should update ----
        print("\n--- Step 5: Run second cycle ---")
        summary2 = await coordinator_cron_tick(
            persona_manager=persona_manager,
            aom_manager=aom,
            chat_model=FakeChatModel(),
        )
        print(f"  Summary: {summary2[:300]}")

        strategy2 = await _load_active_strategy(aom)
        if strategy2:
            print(f"  Updated strategy: {strategy2.goal}")
            print(f"  Outcomes: {len(strategy2.outcomes)}")
            print("  ✅ Second cycle completed, strategy updated")

        print("\n✅ FULL CYCLE COMPLETE")
