# -*- coding: utf-8 -*-
"""Tests for 1C Memory Type Taxonomy."""

import pytest

from adclaw.memory_agent.embeddings import FakeEmbeddingPipeline
from adclaw.memory_agent.ingest import IngestAgent
from adclaw.memory_agent.models import AOMConfig, Memory
from adclaw.memory_agent.query import QueryAgent
from adclaw.memory_agent.store import MemoryStore
from adclaw.memory_agent.type_classifier import (
    classify_memory_type,
    extract_feedback_structure,
)


# ---------------------------------------------------------------------------
# Type Classifier Tests
# ---------------------------------------------------------------------------


class TestClassifyMemoryType:
    def test_feedback_detected(self):
        assert classify_memory_type("Don't use emojis in emails") == "feedback"

    def test_feedback_never_pattern(self):
        assert classify_memory_type("Never send draft without review") == "feedback"

    def test_project_detected(self):
        assert classify_memory_type("Campaign launch deadline is March 15") == "project"

    def test_project_milestone(self):
        assert classify_memory_type("Sprint 3 deliverable: SEO audit report") == "project"

    def test_reference_url(self):
        assert classify_memory_type("Brand guidelines at https://drive.google.com/abc") == "reference"

    def test_reference_doc(self):
        assert classify_memory_type("See the style guide at docs/brand-voice.md") == "reference"

    def test_user_preference(self):
        assert classify_memory_type("I prefer formal tone in all communications") == "user"

    def test_user_background(self):
        assert classify_memory_type("I'm a marketing manager with 10 years experience") == "user"

    def test_default_is_user(self):
        assert classify_memory_type("The sky is blue today") == "user"

    def test_explicit_override_from_metadata(self):
        assert classify_memory_type("anything", {"memory_type": "project"}) == "project"

    def test_feedback_wins_over_project(self):
        # "don't" (feedback) + "deadline" (project) -> feedback wins (priority)
        assert classify_memory_type("Don't miss the deadline, stop procrastinating") == "feedback"


class TestExtractFeedbackStructure:
    def test_with_because(self):
        result = extract_feedback_structure(
            "Don't use emojis in emails because the client considers them unprofessional"
        )
        assert result is not None
        assert "emojis" in result["rule"].lower()
        assert "unprofessional" in result["reason"].lower()

    def test_with_instead(self):
        result = extract_feedback_structure(
            "Wrong approach. Instead use bullet points for clarity"
        )
        assert result is not None
        assert "bullet" in result["application"].lower()

    def test_no_structure_returns_none(self):
        result = extract_feedback_structure("Simple correction note")
        assert result is None


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def store():
    s = MemoryStore(":memory:", dimensions=32)
    await s.initialize()
    yield s
    await s.close()


@pytest.fixture
def embedder():
    return FakeEmbeddingPipeline(dimensions=32)


@pytest.fixture
def config():
    return AOMConfig(enabled=True, embedding_dimensions=32, importance_threshold=0.1)


async def _fake_llm_extract(prompt: str) -> str:
    """Default fake LLM that returns minimal extraction JSON."""
    return '{"entities": [], "topics": [], "importance": 0.5}'


def _make_ingest_agent(
    store: MemoryStore,
    embedder: FakeEmbeddingPipeline,
    config: AOMConfig,
    llm=_fake_llm_extract,
) -> IngestAgent:
    return IngestAgent(store, embedder, llm, config)


# ---------------------------------------------------------------------------
# Store Integration Tests
# ---------------------------------------------------------------------------


class TestMemoryTypeInStore:
    async def test_insert_with_type(self, store):
        mem = Memory(content="User pref", memory_type="user", importance=0.5)
        await store.insert_memory(mem)
        loaded = await store.get_memory(mem.id)
        assert loaded.memory_type == "user"

    async def test_insert_feedback_type(self, store):
        mem = Memory(content="Don't do X", memory_type="feedback", importance=0.8)
        await store.insert_memory(mem)
        loaded = await store.get_memory(mem.id)
        assert loaded.memory_type == "feedback"

    async def test_default_type_is_user(self, store):
        mem = Memory(content="Some memory", importance=0.5)
        await store.insert_memory(mem)
        loaded = await store.get_memory(mem.id)
        assert loaded.memory_type == "user"

    async def test_migration_idempotent(self):
        s = MemoryStore(":memory:", dimensions=32)
        await s.initialize()
        await s.initialize()  # double init
        mem = Memory(content="test", memory_type="project", importance=0.5)
        await s.insert_memory(mem)
        loaded = await s.get_memory(mem.id)
        assert loaded.memory_type == "project"
        await s.close()


# ---------------------------------------------------------------------------
# Ingest Integration Tests
# ---------------------------------------------------------------------------


class TestIngestWithTyping:
    async def test_feedback_auto_classified(self, store, embedder, config):
        async def llm(prompt: str) -> str:
            return '{"entities": [], "topics": ["emails"], "importance": 0.7}'

        agent = _make_ingest_agent(store, embedder, config, llm)
        mem = await agent.ingest("Don't use emojis in client emails because they look unprofessional")
        assert mem.memory_type == "feedback"
        assert "feedback_structure" in mem.metadata

    async def test_project_auto_classified(self, store, embedder, config):
        async def llm(prompt: str) -> str:
            return '{"entities": ["Q2"], "topics": ["campaign"], "importance": 0.6}'

        agent = _make_ingest_agent(store, embedder, config, llm)
        mem = await agent.ingest("Campaign launch deadline is Q2 2026, deliverable is SEO report")
        assert mem.memory_type == "project"

    async def test_reference_auto_classified(self, store, embedder, config):
        async def llm(prompt: str) -> str:
            return '{"entities": [], "topics": ["docs"], "importance": 0.5}'

        agent = _make_ingest_agent(store, embedder, config, llm)
        mem = await agent.ingest("Brand guidelines at https://drive.google.com/brand-guide")
        assert mem.memory_type == "reference"

    async def test_explicit_type_override(self, store, embedder, config):
        agent = _make_ingest_agent(store, embedder, config)
        mem = await agent.ingest("Anything", metadata={"memory_type": "project"})
        assert mem.memory_type == "project"


# ---------------------------------------------------------------------------
# Query Boost Tests
# ---------------------------------------------------------------------------


class TestQueryFeedbackBoost:
    async def test_feedback_boosted_in_results(self, store, embedder):
        async def fake_llm(prompt: str) -> str:
            return "Based on memories, the answer is test."

        query_config = AOMConfig(enabled=True, embedding_dimensions=32)

        fb = Memory(content="Never use passive voice in emails", memory_type="feedback", importance=0.8)
        user = Memory(content="Email writing tips and best practices", memory_type="user", importance=0.5)
        await store.insert_memory(fb, embedding=await embedder.embed(fb.content))
        await store.insert_memory(user, embedding=await embedder.embed(user.content))

        agent = QueryAgent(store, embedder, fake_llm, query_config)
        result = await agent.query("How should I write emails?", skip_synthesis=True)

        # Feedback memory should be ranked first (boosted score)
        assert len(result.citations) >= 2, f"Expected >= 2 citations, got {len(result.citations)}"
        assert result.citations[0].memory.memory_type == "feedback"
