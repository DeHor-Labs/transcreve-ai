"""
EmbeddingStore - armazenamento e busca de embeddings em SQLite.

Tabela `embeddings` adicionada ao mesmo index.db do RunIndex.
Busca cosine em Python com numpy (importado lazy dentro de search()).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .chunker import EmbeddingChunk

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_EMBED_DDL = """
CREATE TABLE IF NOT EXISTS embeddings (
    id            TEXT NOT NULL PRIMARY KEY,
    run_id        TEXT NOT NULL,
    chunk_index   INTEGER NOT NULL,
    chunk_type    TEXT NOT NULL,
    chunk_text    TEXT NOT NULL,
    embedding     BLOB NOT NULL,
    model         TEXT NOT NULL,
    dim           INTEGER NOT NULL,
    provider      TEXT NOT NULL,
    chapter_start REAL,
    source_title  TEXT NOT NULL DEFAULT '',
    source_url    TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_emb_run_id ON embeddings (run_id);
CREATE INDEX IF NOT EXISTS idx_emb_type   ON embeddings (chunk_type);
"""


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass
class SearchHit:
    """Resultado de uma busca por similaridade."""

    run_id: str
    title: str
    source_url: str
    chunk_type: str
    excerpt: str
    score: float
    chapter_start: float | None


# ---------------------------------------------------------------------------
# EmbeddingStore
# ---------------------------------------------------------------------------


class EmbeddingStore:
    """
    Gerenciador de contexto para a tabela de embeddings.

    Uso:
        with EmbeddingStore(db_path) as store:
            store.upsert_chunks(run_id, chunks, vectors, provider, model)
            hits = store.search(query_vec, limit=5)
    """

    def __init__(self, db_path: Path | None = None) -> None:
        from ..index import resolve_index_path

        self._db_path: Path = db_path or resolve_index_path()
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Gerenciamento de conexao
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(self._db_path),
            timeout=10,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(_EMBED_DDL)
        conn.commit()
        self._conn = conn
        return conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> EmbeddingStore:
        self._connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def has_indexed(self, run_id: str) -> bool:
        """Retorna True se ja existem embeddings para este run_id."""
        conn = self._connect()
        row = conn.execute(
            "SELECT 1 FROM embeddings WHERE run_id = ? LIMIT 1",
            (run_id,),
        ).fetchone()
        return row is not None

    def delete_run(self, run_id: str) -> int:
        """Remove todos os embeddings de um run. Retorna quantidade removida."""
        conn = self._connect()
        cursor = conn.execute(
            "DELETE FROM embeddings WHERE run_id = ?",
            (run_id,),
        )
        conn.commit()
        return cursor.rowcount

    def upsert_chunks(
        self,
        run_id: str,
        chunks: list[EmbeddingChunk],
        vectors: list[list[float]],
        provider: str,
        model: str,
        force: bool = False,
    ) -> int:
        """
        Grava chunks e seus vetores no banco.

        Args:
            run_id: ID do run.
            chunks: lista de EmbeddingChunk gerada pelo chunker.
            vectors: lista de vetores na mesma ordem de chunks.
            provider: nome do provider (ex: "openai").
            model: nome do modelo de embedding (ex: "text-embedding-3-small").
            force: se True, deleta embeddings existentes antes de inserir.

        Returns:
            Numero de chunks gravados.

        Raises:
            DimMismatchError: se ja existe indexacao com dimensao diferente.
        """
        if not chunks:
            return 0

        if len(chunks) != len(vectors):
            raise ValueError(
                f"chunks ({len(chunks)}) e vectors ({len(vectors)}) devem ter o mesmo tamanho."
            )

        dim = len(vectors[0])
        conn = self._connect()

        if not force and self.has_indexed(run_id):
            # Verifica se a dimensao ja armazenada bate com a atual
            existing_row = conn.execute(
                "SELECT dim FROM embeddings WHERE run_id = ? LIMIT 1",
                (run_id,),
            ).fetchone()
            if existing_row and existing_row["dim"] != dim:
                raise DimMismatchError(
                    run_id=run_id,
                    existing_dim=existing_row["dim"],
                    new_dim=dim,
                )
            # Ja indexado, nao --force: pula sem erro (quem decide eh o chamador)
            return 0

        if force:
            self.delete_run(run_id)

        ts = _iso_now()
        rows = []
        for chunk, vec in zip(chunks, vectors):
            rows.append(
                (
                    chunk.chunk_id,
                    chunk.run_id,
                    chunk.chunk_index,
                    chunk.chunk_type,
                    chunk.chunk_text,
                    json.dumps(vec).encode("utf-8"),
                    model,
                    dim,
                    provider,
                    chunk.chapter_start,
                    chunk.source_title,
                    chunk.source_url,
                    ts,
                )
            )

        conn.executemany(
            """
            INSERT OR REPLACE INTO embeddings (
                id, run_id, chunk_index, chunk_type, chunk_text,
                embedding, model, dim, provider,
                chapter_start, source_title, source_url, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        return len(rows)

    def search(
        self,
        query_vec: list[float],
        limit: int = 5,
        run_ids: list[str] | None = None,
    ) -> list[SearchHit]:
        """
        Busca os top-k chunks mais similares ao vetor de consulta.

        numpy importado lazy aqui para nao exigir a dependencia no import do pacote.

        Args:
            query_vec: vetor de embedding da query.
            limit: numero maximo de resultados.
            run_ids: se fornecido, restringe a busca a estes run_ids.

        Returns:
            Lista de SearchHit ordenada por score decrescente.
        """
        import numpy as np  # lazy import - requer extra [rag]

        conn = self._connect()

        if run_ids is not None and not run_ids:
            return []

        if run_ids is not None:
            placeholders = ",".join("?" * len(run_ids))
            rows = conn.execute(
                f"SELECT * FROM embeddings WHERE run_id IN ({placeholders})",  # noqa: S608
                list(run_ids),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM embeddings").fetchall()

        if not rows:
            return []

        q = np.array(query_vec, dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            return []

        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            vec = np.array(json.loads(row["embedding"]), dtype=np.float32)
            v_norm = np.linalg.norm(vec)
            if v_norm == 0:
                continue
            score = float(np.dot(q, vec) / (q_norm * v_norm))
            scored.append((score, row))

        scored.sort(key=lambda t: t[0], reverse=True)

        hits: list[SearchHit] = []
        for score, row in scored[:limit]:
            hits.append(
                SearchHit(
                    run_id=row["run_id"],
                    title=row["source_title"] or "",
                    source_url=row["source_url"] or "",
                    chunk_type=row["chunk_type"],
                    excerpt=row["chunk_text"][:200],
                    score=score,
                    chapter_start=row["chapter_start"],
                )
            )

        return hits


# ---------------------------------------------------------------------------
# Excecoes
# ---------------------------------------------------------------------------


class DimMismatchError(RuntimeError):
    """
    Levantada quando o provider atual gera vetores com dimensao diferente
    dos ja armazenados para o mesmo run_id.
    """

    def __init__(self, run_id: str, existing_dim: int, new_dim: int) -> None:
        self.run_id = run_id
        self.existing_dim = existing_dim
        self.new_dim = new_dim
        super().__init__(
            f"Run '{run_id}' ja indexado com dim={existing_dim}, "
            f"mas o provider atual gera dim={new_dim}. "
            "Use 'transcreveai index <run_id> --force' para reindexar."
        )


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()
