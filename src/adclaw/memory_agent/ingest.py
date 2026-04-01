# -*- coding: utf-8 -*-
"""IngestAgent — captures content into the memory store with LLM extraction."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Coroutine, List, Optional

from .dedup import ShingleCache, find_near_duplicate
from .embeddings import EmbeddingPipeline
from .models import AOMConfig, Memory
from .multimodal import MultimodalProcessor, is_multimodal_file, is_supported_file
from .sanitizer import MemorySanitizer
from .store import MemoryStore
from .type_classifier import classify_memory_type, extract_feedback_structure

logger = logging.getLogger(__name__)

# Default extraction prompt
_EXTRACT_PROMPT = """Extract structured metadata from the following content.
Return ONLY a JSON object with these fields:
- "entities": list of named entities (people, companies, tools, URLs)
- "topics": list of topic tags
- "importance": float 0.0-1.0 (how valuable is this information)

Content:
{content}

JSON:"""


class IngestAgent:
    """Processes raw content into structured memories with embeddings."""

    def __init__(
        self,
        store: MemoryStore,
        embedder: EmbeddingPipeline,
        llm_caller: Callable[[str], Coroutine[Any, Any, str]],
        config: Optional[AOMConfig] = None,
        multimodal: Optional[MultimodalProcessor] = None,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.llm_caller = llm_caller
        self.config = config or AOMConfig()
        self.multimodal = multimodal
        self._sanitizer = MemorySanitizer(mode="block")
        self._shingle_cache = ShingleCache(max_size=200)
        self._on_memory_inserted: Optional[Callable[[], None]] = None

    async def ingest(
        self,
        content: str,
        source_type: str = "manual",
        source_id: str = "",
        skip_llm: bool = False,
        metadata: Optional[dict] = None,
    ) -> Memory:
        """Ingest a single piece of content into memory store."""
        if not content or not content.strip():
            raise ValueError("Empty content cannot be ingested")

        # Sanitize content for prompt injection
        san_result = self._sanitizer.sanitize(content)
        if not san_result.safe:
            threat_ids = ", ".join(san_result.threat_ids)
            logger.warning(
                "Memory injection blocked from %s/%s: %s",
                source_type,
                source_id,
                threat_ids,
            )
            raise ValueError(
                f"Content blocked by memory sanitizer: {threat_ids}"
            )
        if san_result.threats:
            # Warnings — store but tag in metadata
            metadata = metadata or {}
            metadata["sanitizer_warnings"] = [
                {"id": t.threat_id, "desc": t.description}
                for t in san_result.threats
            ]

        entities: List[str] = []
        topics: List[str] = []
        importance = 0.5

        if not skip_llm:
            try:
                extracted = await self._extract_structured(content)
                entities = extracted.get("entities", [])
                topics = extracted.get("topics", [])
                importance = float(extracted.get("importance", 0.5))
            except Exception as exc:
                logger.warning("LLM extraction failed: %s", exc)

        # Filter by importance threshold
        if importance < self.config.importance_threshold:
            importance = self.config.importance_threshold

        # R3: Near-duplicate detection (catches paraphrases SHA-256 misses)
        try:
            recent = await self.store.recent_memories(limit=100)
            existing_entries = [(m.id, m.content) for m in recent]
            dup_id = find_near_duplicate(
                content,
                existing_entries,
                threshold=0.6,
                cache=self._shingle_cache,
            )
            if dup_id:
                logger.info(
                    "Near-duplicate detected (match=%s), skipping ingest",
                    dup_id[:12],
                )
                existing_mem = await self.store.get_memory(dup_id)
                if existing_mem:
                    return existing_mem
        except Exception as exc:
            logger.debug("Near-dedup check failed (non-fatal): %s", exc)

        # Classify memory type
        memory_type = classify_memory_type(content, metadata)

        # Extract feedback structure if applicable
        if memory_type == "feedback":
            fb_structure = extract_feedback_structure(content)
            if fb_structure:
                metadata = metadata or {}
                metadata["feedback_structure"] = fb_structure

        memory = Memory(
            content=content,
            source_type=source_type,
            source_id=source_id,
            entities=entities,
            topics=topics,
            importance=importance,
            metadata=metadata or {},
            memory_type=memory_type,
        )

        # Generate embedding
        try:
            embedding = await self.embedder.embed(content)
        except Exception as exc:
            logger.warning("Embedding failed: %s", exc)
            embedding = None

        result = await self.store.insert_memory(memory, embedding=embedding)
        # Only notify if this is a genuinely new memory (not a dedup hit)
        if self._on_memory_inserted and result.id == memory.id:
            self._on_memory_inserted()
        return result

    async def ingest_file(
        self,
        file_path: Path | str,
        source_id: str = "",
    ) -> Memory:
        """Ingest a file — text directly, multimodal via vision LLM.

        Args:
            file_path: Path to the file.
            source_id: Override source ID (default: filename).

        Returns:
            The created Memory.

        Raises:
            ValueError: If file type not supported.
            RuntimeError: If multimodal file but no API key.
        """
        fp = Path(file_path)
        if not source_id:
            source_id = fp.name

        if not is_supported_file(fp):
            raise ValueError(f"Unsupported file type: {fp.suffix}")

        if is_multimodal_file(fp):
            # Requires multimodal processor with API key
            if not self.multimodal or not self.multimodal.is_available:
                raise RuntimeError(
                    f"File {fp.name} requires multimodal processing. "
                    f"Set multimodal_api_key in AOM config."
                )
            content = await self.multimodal.process_file(fp)
            metadata = {
                "original_file": fp.name,
                "file_type": fp.suffix.lower(),
                "processed_by": f"{self.multimodal.provider}/{self.multimodal.model}",
            }
        else:
            # Text file — read directly
            content = fp.read_text(encoding="utf-8", errors="replace")
            metadata = {"original_file": fp.name, "file_type": fp.suffix.lower()}

        return await self.ingest(
            content=content,
            source_type="file_inbox",
            source_id=source_id,
            metadata=metadata,
        )

    async def ingest_batch(
        self,
        items: List[dict],
        skip_llm: bool = False,
    ) -> List[Memory]:
        """Batch ingest. Each item: {content, source_type?, source_id?, metadata?}."""
        results = []
        for item in items:
            try:
                mem = await self.ingest(
                    content=item["content"],
                    source_type=item.get("source_type", "manual"),
                    source_id=item.get("source_id", ""),
                    skip_llm=skip_llm,
                    metadata=item.get("metadata"),
                )
                results.append(mem)
            except Exception as exc:
                logger.warning("Batch ingest item failed: %s", exc)
        return results

    async def _extract_structured(self, content: str) -> dict:
        """Use LLM to extract entities, topics, importance."""
        prompt = _EXTRACT_PROMPT.format(content=content[:2000])
        raw = await self.llm_caller(prompt)

        # Try to parse JSON from response
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw

        return json.loads(raw)

    def _content_hash(self, content: str) -> str:
        import hashlib

        return hashlib.sha256(content.encode()).hexdigest()
