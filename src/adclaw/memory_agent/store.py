# -*- coding: utf-8 -*-
"""MemoryStore — SQLite + sqlite-vec + FTS5 persistent memory storage."""

from __future__ import annotations

import hashlib
import json
import logging
import struct
from pathlib import Path
from typing import List, Optional, Tuple

import aiosqlite

from .models import Consolidation, Memory, _utcnow

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_f32(vec: List[float]) -> bytes:
    """Pack a list of floats into little-endian float32 bytes for sqlite-vec."""
    return struct.pack(f"<{len(vec)}f", *vec)


def _deserialize_f32(blob: bytes, dims: int) -> List[float]:
    return list(struct.unpack(f"<{dims}f", blob))


# ---------------------------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------------------------

class MemoryStore:
    """Async SQLite store with sqlite-vec virtual table and FTS5 index."""

    def __init__(self, db_path: Path | str, dimensions: int = 384) -> None:
        self._db_path = str(db_path)
        self._dimensions = dimensions
        self._db: Optional[aiosqlite.Connection] = None

    # ------ lifecycle ------

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")

        # Load sqlite-vec extension
        await self._db.enable_load_extension(True)
        try:
            import sqlite_vec  # noqa: F811

            vec_path = sqlite_vec.loadable_path()
            await self._db.load_extension(vec_path)
            logger.debug("sqlite-vec loaded from %s", vec_path)
        except Exception as exc:
            logger.warning("sqlite-vec unavailable (%s); vector search disabled", exc)

        await self._create_tables()
        await self._migrate_v2()
        await self._db.commit()

    async def _create_tables(self) -> None:
        assert self._db is not None

        await self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id               TEXT PRIMARY KEY,
                content          TEXT NOT NULL,
                content_hash     TEXT,
                source_type      TEXT NOT NULL DEFAULT 'manual',
                source_id        TEXT DEFAULT '',
                entities         TEXT DEFAULT '[]',
                topics           TEXT DEFAULT '[]',
                importance       REAL DEFAULT 0.5,
                metadata         TEXT DEFAULT '{}',
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL,
                is_deleted       INTEGER DEFAULT 0,
                last_consolidated_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_memories_hash
                ON memories(content_hash);
            CREATE INDEX IF NOT EXISTS idx_memories_source
                ON memories(source_type, is_deleted);
            CREATE INDEX IF NOT EXISTS idx_memories_importance
                ON memories(importance DESC);

            CREATE TABLE IF NOT EXISTS embeddings (
                memory_id   TEXT PRIMARY KEY REFERENCES memories(id),
                vector      BLOB NOT NULL,
                model_name  TEXT NOT NULL,
                dimensions  INTEGER NOT NULL,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS consolidations (
                id          TEXT PRIMARY KEY,
                insight     TEXT NOT NULL,
                memory_ids  TEXT NOT NULL,
                importance  REAL DEFAULT 0.5,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS processed_files (
                file_path   TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL
            );
            """
        )

        # FTS5 virtual table (ignore error if exists)
        try:
            await self._db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts "
                "USING fts5(content, entities, topics, content='memories', "
                "content_rowid='rowid')"
            )
        except Exception:
            pass  # already exists or FTS5 not available

        # sqlite-vec virtual table
        try:
            await self._db.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_memories "
                f"USING vec0(memory_id TEXT PRIMARY KEY, "
                f"embedding float[{self._dimensions}])"
            )
        except Exception as exc:
            logger.debug("vec0 table creation skipped: %s", exc)

    async def _migrate_v2(self) -> None:
        """Add v2 columns. Silently skips if column already exists; logs other errors."""
        assert self._db is not None
        for col, col_type in [
            ("last_verified_at", "TEXT"),
            ("superseded_by", "TEXT"),
            ("memory_type", "TEXT DEFAULT 'user'"),
        ]:
            try:
                await self._db.execute(
                    f"ALTER TABLE memories ADD COLUMN {col} {col_type}"
                )
            except Exception as exc:
                if "duplicate column" in str(exc).lower():
                    pass  # column already exists
                else:
                    logger.error("_migrate_v2: unexpected error adding column %s: %s", col, exc)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    # ------ CRUD memories ------

    async def insert_memory(
        self,
        memory: Memory,
        embedding: Optional[List[float]] = None,
    ) -> Memory:
        assert self._db is not None

        # Dedup check
        existing = await self._db.execute_fetchall(
            "SELECT id FROM memories WHERE content_hash = ? AND is_deleted = 0",
            (memory.content_hash,),
        )
        if existing:
            logger.debug("Duplicate memory (hash=%s), returning existing", memory.content_hash[:12])
            return await self.get_memory(existing[0][0])  # type: ignore[index]

        await self._db.execute(
            """INSERT INTO memories
               (id, content, content_hash, source_type, source_id,
                entities, topics, importance, metadata,
                created_at, updated_at, is_deleted, last_consolidated_at,
                last_verified_at, superseded_by, memory_type)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                memory.id,
                memory.content,
                memory.content_hash,
                memory.source_type,
                memory.source_id,
                json.dumps(memory.entities),
                json.dumps(memory.topics),
                memory.importance,
                json.dumps(memory.metadata),
                memory.created_at,
                memory.updated_at,
                memory.is_deleted,
                memory.last_consolidated_at,
                memory.last_verified_at,
                memory.superseded_by,
                memory.memory_type,
            ),
        )

        # FTS sync
        try:
            await self._db.execute(
                "INSERT INTO memories_fts(rowid, content, entities, topics) "
                "VALUES ((SELECT rowid FROM memories WHERE id=?), ?, ?, ?)",
                (
                    memory.id,
                    memory.content,
                    json.dumps(memory.entities),
                    json.dumps(memory.topics),
                ),
            )
        except Exception:
            pass

        # Embedding
        if embedding is not None:
            await self.upsert_embedding(memory.id, embedding, "unknown")

        await self._db.commit()
        return memory

    async def get_memory(self, memory_id: str) -> Optional[Memory]:
        assert self._db is not None
        row = await self._db.execute_fetchall(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        )
        if not row:
            return None
        return self._row_to_memory(row[0])

    async def list_memories(
        self,
        source_type: Optional[str] = None,
        limit: int = 50,
        min_importance: float = 0.0,
    ) -> List[Memory]:
        assert self._db is not None
        query = "SELECT * FROM memories WHERE is_deleted = 0 AND importance >= ?"
        params: list = [min_importance]
        if source_type:
            query += " AND source_type = ?"
            params.append(source_type)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = await self._db.execute_fetchall(query, params)
        return [self._row_to_memory(r) for r in rows]

    async def delete_memory(self, memory_id: str, hard: bool = False) -> bool:
        assert self._db is not None
        if hard:
            await self._db.execute("DELETE FROM embeddings WHERE memory_id = ?", (memory_id,))
            try:
                await self._db.execute(
                    "DELETE FROM vec_memories WHERE memory_id = ?", (memory_id,)
                )
            except Exception:
                pass
            cur = await self._db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        else:
            cur = await self._db.execute(
                "UPDATE memories SET is_deleted = 1, updated_at = ? WHERE id = ?",
                (_utcnow(), memory_id),
            )
        await self._db.commit()
        return cur.rowcount > 0

    async def recent_memories(self, limit: int = 100) -> List[Memory]:
        """Return most recent non-deleted memories (for near-dedup checks)."""
        assert self._db is not None
        rows = await self._db.execute_fetchall(
            "SELECT * FROM memories WHERE is_deleted = 0 "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [self._row_to_memory(r) for r in rows]

    async def update_memory_content(
        self, memory_id: str, content: str
    ) -> bool:
        """Update memory content (used by temporal pruning condensation)."""
        assert self._db is not None
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        cur = await self._db.execute(
            "UPDATE memories SET content = ?, content_hash = ?, updated_at = ? "
            "WHERE id = ?",
            (content, content_hash, _utcnow(), memory_id),
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def get_unconsolidated_memories(self, limit: int = 50) -> List[Memory]:
        assert self._db is not None
        rows = await self._db.execute_fetchall(
            "SELECT * FROM memories WHERE is_deleted = 0 "
            "AND last_consolidated_at IS NULL "
            "ORDER BY importance DESC LIMIT ?",
            (limit,),
        )
        return [self._row_to_memory(r) for r in rows]

    async def mark_consolidated(self, memory_ids: List[str]) -> None:
        assert self._db is not None
        now = _utcnow()
        for mid in memory_ids:
            await self._db.execute(
                "UPDATE memories SET last_consolidated_at = ? WHERE id = ?",
                (now, mid),
            )
        await self._db.commit()

    # ------ embeddings ------

    async def upsert_embedding(
        self,
        memory_id: str,
        vector: List[float],
        model_name: str,
    ) -> None:
        assert self._db is not None
        blob = _serialize_f32(vector)
        dims = len(vector)
        now = _utcnow()

        await self._db.execute(
            "INSERT OR REPLACE INTO embeddings (memory_id, vector, model_name, dimensions, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (memory_id, blob, model_name, dims, now),
        )

        # Insert into vec0
        try:
            await self._db.execute(
                "INSERT OR REPLACE INTO vec_memories (memory_id, embedding) VALUES (?, ?)",
                (memory_id, blob),
            )
        except Exception:
            pass

        await self._db.commit()

    async def vector_search(
        self,
        query_vector: List[float],
        limit: int = 10,
    ) -> List[Tuple[str, float]]:
        """Return list of (memory_id, distance) sorted by ascending distance."""
        assert self._db is not None
        blob = _serialize_f32(query_vector)
        try:
            rows = await self._db.execute_fetchall(
                "SELECT memory_id, distance FROM vec_memories "
                "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (blob, limit),
            )
            return [(r[0], float(r[1])) for r in rows]
        except Exception as exc:
            logger.warning("vector_search fallback (brute-force): %s", exc)
            return await self._brute_force_vector_search(query_vector, limit)

    async def _brute_force_vector_search(
        self,
        query_vector: List[float],
        limit: int,
    ) -> List[Tuple[str, float]]:
        """Fallback cosine-similarity search when sqlite-vec is unavailable."""
        assert self._db is not None
        rows = await self._db.execute_fetchall(
            "SELECT e.memory_id, e.vector, e.dimensions FROM embeddings e "
            "JOIN memories m ON e.memory_id = m.id WHERE m.is_deleted = 0"
        )
        import math

        results: list[Tuple[str, float]] = []
        for r in rows:
            vec = _deserialize_f32(r[1], int(r[2]))
            # cosine distance
            dot = sum(a * b for a, b in zip(query_vector, vec))
            norm_q = math.sqrt(sum(a * a for a in query_vector))
            norm_v = math.sqrt(sum(a * a for a in vec))
            if norm_q == 0 or norm_v == 0:
                dist = 1.0
            else:
                dist = 1.0 - (dot / (norm_q * norm_v))
            results.append((r[0], dist))

        results.sort(key=lambda x: x[1])
        return results[:limit]

    # ------ keyword search (FTS5) ------

    async def keyword_search(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Tuple[str, float]]:
        """Return list of (memory_id, rank) from FTS5 search."""
        assert self._db is not None
        try:
            rows = await self._db.execute_fetchall(
                "SELECT m.id, fts.rank FROM memories_fts fts "
                "JOIN memories m ON m.rowid = fts.rowid "
                "WHERE memories_fts MATCH ? AND m.is_deleted = 0 "
                "ORDER BY fts.rank LIMIT ?",
                (query, limit),
            )
            return [(r[0], float(r[1])) for r in rows]
        except Exception as exc:
            logger.warning("FTS5 search failed, using LIKE fallback: %s", exc)
            return await self._fallback_keyword_search(query, limit)

    async def _fallback_keyword_search(
        self,
        query: str,
        limit: int,
    ) -> List[Tuple[str, float]]:
        """LIKE-based fallback when FTS5 is unavailable."""
        assert self._db is not None
        pattern = f"%{query}%"
        rows = await self._db.execute_fetchall(
            "SELECT id FROM memories WHERE is_deleted = 0 AND "
            "(content LIKE ? OR entities LIKE ? OR topics LIKE ?) LIMIT ?",
            (pattern, pattern, pattern, limit),
        )
        return [(r[0], 0.0) for r in rows]

    # ------ consolidations ------

    async def insert_consolidation(self, consolidation: Consolidation) -> Consolidation:
        assert self._db is not None
        await self._db.execute(
            "INSERT INTO consolidations (id, insight, memory_ids, importance, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                consolidation.id,
                consolidation.insight,
                json.dumps(consolidation.memory_ids),
                consolidation.importance,
                consolidation.created_at,
            ),
        )
        await self._db.commit()
        return consolidation

    async def list_consolidations(self, limit: int = 50) -> List[Consolidation]:
        assert self._db is not None
        rows = await self._db.execute_fetchall(
            "SELECT * FROM consolidations ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [
            Consolidation(
                id=r[0],
                insight=r[1],
                memory_ids=json.loads(r[2]),
                importance=float(r[3]),
                created_at=r[4],
            )
            for r in rows
        ]

    # ------ stats ------

    async def get_stats(self) -> dict:
        assert self._db is not None
        total = (await self._db.execute_fetchall(
            "SELECT COUNT(*) FROM memories WHERE is_deleted = 0"
        ))[0][0]
        with_emb = (await self._db.execute_fetchall(
            "SELECT COUNT(*) FROM embeddings"
        ))[0][0]
        cons = (await self._db.execute_fetchall(
            "SELECT COUNT(*) FROM consolidations"
        ))[0][0]
        by_source = {}
        rows = await self._db.execute_fetchall(
            "SELECT source_type, COUNT(*) FROM memories "
            "WHERE is_deleted = 0 GROUP BY source_type"
        )
        for r in rows:
            by_source[r[0]] = r[1]
        return {
            "total_memories": total,
            "with_embeddings": with_emb,
            "consolidations": cons,
            "by_source": by_source,
        }

    # ------ processed files tracking ------

    async def is_file_processed(self, file_path: str) -> bool:
        assert self._db is not None
        rows = await self._db.execute_fetchall(
            "SELECT 1 FROM processed_files WHERE file_path = ?", (file_path,)
        )
        return len(rows) > 0

    async def mark_file_processed(self, file_path: str) -> None:
        assert self._db is not None
        await self._db.execute(
            "INSERT OR REPLACE INTO processed_files (file_path, processed_at) VALUES (?, ?)",
            (file_path, _utcnow()),
        )
        await self._db.commit()

    # ------ v2: consolidation gate helpers ------

    async def count_memories(self, include_deleted: bool = False) -> int:
        assert self._db is not None
        q = "SELECT COUNT(*) FROM memories"
        if not include_deleted:
            q += " WHERE is_deleted = 0"
        rows = await self._db.execute_fetchall(q)
        return rows[0][0]

    async def mark_verified(self, memory_ids: List[str]) -> None:
        assert self._db is not None
        now = _utcnow()
        for mid in memory_ids:
            await self._db.execute(
                "UPDATE memories SET last_verified_at = ? WHERE id = ?",
                (now, mid),
            )
        await self._db.commit()

    async def mark_superseded(self, loser_id: str, winner_id: str) -> None:
        assert self._db is not None
        await self._db.execute(
            "UPDATE memories SET superseded_by = ?, is_deleted = 1, updated_at = ? WHERE id = ?",
            (winner_id, _utcnow(), loser_id),
        )
        await self._db.commit()

    async def cleanup_orphan_consolidations(self) -> int:
        """Delete consolidations where all source memories are soft-deleted."""
        assert self._db is not None
        cons = await self.list_consolidations(limit=500)
        removed = 0
        for c in cons:
            all_deleted = True
            for mid in c.memory_ids:
                mem = await self.get_memory(mid)
                if mem and mem.is_deleted == 0:
                    all_deleted = False
                    break
            if all_deleted:
                await self._db.execute(
                    "DELETE FROM consolidations WHERE id = ?", (c.id,)
                )
                removed += 1
        if removed:
            await self._db.commit()
        return removed

    # ------ helpers ------

    @staticmethod
    def _row_to_memory(row) -> Memory:
        return Memory(
            id=row[0],
            content=row[1],
            content_hash=row[2] or "",
            source_type=row[3],
            source_id=row[4] or "",
            entities=json.loads(row[5]) if row[5] else [],
            topics=json.loads(row[6]) if row[6] else [],
            importance=float(row[7]),
            metadata=json.loads(row[8]) if row[8] else {},
            created_at=row[9],
            updated_at=row[10],
            is_deleted=int(row[11]),
            last_consolidated_at=row[12],
            last_verified_at=row[13] if len(row) > 13 else None,
            superseded_by=row[14] if len(row) > 14 else None,
            memory_type=row[15] if len(row) > 15 else "user",
        )
