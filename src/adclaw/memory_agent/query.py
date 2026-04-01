# -*- coding: utf-8 -*-
"""QueryAgent — hybrid search (vector + keyword + RRF) with LLM synthesis."""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine, List, Optional

from .embeddings import EmbeddingPipeline
from .models import AOMConfig, MemorySearchResult, QueryResult
from .store import MemoryStore

logger = logging.getLogger(__name__)

# Feedback memories get a score boost so corrections rank higher in results
_FEEDBACK_BOOST = 1.5

_SYNTHESIS_PROMPT = """You are a memory retrieval assistant. Based on the following memory entries,
answer the user's question. Cite memories using [Memory #<id>] format.

Question: {question}

Relevant Memories:
{memories}

Answer concisely, citing the most relevant memories:"""


def _reciprocal_rank_fusion(
    *result_lists: List[tuple[str, float]],
    k: int = 60,
) -> List[tuple[str, float]]:
    """Merge multiple ranked lists using Reciprocal Rank Fusion.

    Args:
        result_lists: Each is a list of (id, score) tuples (lower = better for vector).
        k: RRF constant (default 60).

    Returns:
        Merged list of (id, rrf_score) sorted descending by score.
    """
    scores: dict[str, float] = {}
    for results in result_lists:
        for rank, (doc_id, _) in enumerate(results):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_items


class QueryAgent:
    """Hybrid search + LLM synthesis for memory queries."""

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

    async def query(
        self,
        question: str,
        max_results: int = 10,
        skip_synthesis: bool = False,
    ) -> QueryResult:
        """Run hybrid search and synthesize an answer.

        Args:
            question: The user's question.
            max_results: Max memories to retrieve.
            skip_synthesis: If True, skip LLM synthesis and return raw results.
        """
        # 1. Embed the question
        try:
            query_vec = await self.embedder.embed(question)
            vec_results = await self.store.vector_search(query_vec, limit=max_results * 2)
        except Exception as exc:
            logger.warning("Vector search failed: %s", exc)
            vec_results = []

        # 2. Keyword search
        try:
            kw_results = await self.store.keyword_search(question, limit=max_results * 2)
        except Exception:
            kw_results = []

        # 3. RRF merge
        if vec_results or kw_results:
            merged = _reciprocal_rank_fusion(vec_results, kw_results)
        else:
            merged = []

        # 4. Fetch memories, apply feedback boost, THEN slice to max_results
        # Fetch extra candidates so boosted feedback can be promoted into top-N
        fetch_limit = min(max_results * 2, len(merged))
        candidates: List[MemorySearchResult] = []
        for doc_id, score in merged[:fetch_limit]:
            mem = await self.store.get_memory(doc_id)
            if mem and mem.is_deleted == 0:
                boosted_score = score * _FEEDBACK_BOOST if mem.memory_type == "feedback" else score
                candidates.append(MemorySearchResult(memory=mem, score=boosted_score))
        # Sort by boosted score, then slice to max_results
        candidates.sort(key=lambda c: c.score, reverse=True)
        citations = candidates[:max_results]

        # 5. Fetch consolidations
        consolidations = await self.store.list_consolidations(limit=5)

        if not citations:
            return QueryResult(
                answer="No relevant memories found.",
                citations=[],
                consolidations=consolidations,
            )

        if skip_synthesis:
            return QueryResult(
                answer="",
                citations=citations,
                consolidations=consolidations,
            )

        # 6. LLM synthesis
        memories_text = "\n".join(
            f"[Memory #{c.memory.id[:8]}] ({c.memory.source_type}/{c.memory.source_id}) "
            f"{c.memory.content[:500]}"
            for c in citations
        )
        prompt = _SYNTHESIS_PROMPT.format(
            question=question,
            memories=memories_text,
        )
        answer = await self.llm_caller(prompt)

        return QueryResult(
            answer=answer.strip(),
            citations=citations,
            consolidations=consolidations,
        )
