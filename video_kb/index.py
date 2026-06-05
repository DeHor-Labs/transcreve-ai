"""
Indice de runs do TranscreveAI.

Armazena metadados de cada run em SQLite para dedupe,
listagem e recuperacao de historico. Toda falha do banco e
tratada de forma gracil: o pipeline continua sem interrupção.

Localizacao padrao: ~/.transcreveai/index.db
Override: env VIDEO_KB_INDEX_DB ou parametro cli_flag.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Resolucao de caminho
# ---------------------------------------------------------------------------

_ENV_KEY = "VIDEO_KB_INDEX_DB"
_DEFAULT_DB_DIR = Path.home() / ".transcreveai"
_DEFAULT_DB_NAME = "index.db"


def resolve_index_path(cli_flag: str | None = None) -> Path:
    """
    Retorna o caminho do banco SQLite seguindo a precedencia:
    1. Argumento cli_flag (flag --index-db do CLI)
    2. Variavel de ambiente VIDEO_KB_INDEX_DB
    3. ~/.transcreveai/index.db
    """
    raw = cli_flag or os.environ.get(_ENV_KEY) or ""
    if raw:
        return Path(raw).expanduser().resolve()
    return _DEFAULT_DB_DIR / _DEFAULT_DB_NAME


# ---------------------------------------------------------------------------
# Excecao de run duplicado
# ---------------------------------------------------------------------------


class DuplicateRunError(RuntimeError):
    """
    Levantada quando um run com o mesmo source_hash ja existe no indice
    e --force nao foi passado.

    O atributo `existing` contem o dict com os campos do run pre-existente.
    """

    def __init__(self, existing: dict[str, Any]) -> None:
        self.existing = existing
        run_id = existing.get("id", "?")
        output_dir = existing.get("output_dir", "?")
        super().__init__(
            f"Run duplicado: '{run_id}' em '{output_dir}'. Use --force para reprocessar."
        )


# ---------------------------------------------------------------------------
# Schema SQL
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    id               TEXT    NOT NULL PRIMARY KEY,
    source           TEXT    NOT NULL,
    source_hash      TEXT    NOT NULL,
    title            TEXT    NOT NULL DEFAULT '',
    provider         TEXT    NOT NULL DEFAULT '',
    ai_mode          TEXT    NOT NULL DEFAULT '',
    status           TEXT    NOT NULL DEFAULT 'completed',
    created_at       TEXT    NOT NULL,
    finished_at      TEXT    NOT NULL DEFAULT '',
    output_dir       TEXT    NOT NULL DEFAULT '',
    analysis_path    TEXT    NOT NULL DEFAULT '',
    markdown_path    TEXT    NOT NULL DEFAULT '',
    duration_seconds REAL    NOT NULL DEFAULT 0.0,
    warnings_count   INTEGER NOT NULL DEFAULT 0,
    storage_backend  TEXT    NOT NULL DEFAULT 'filesystem'
);

CREATE INDEX IF NOT EXISTS idx_runs_source_hash ON runs (source_hash);
CREATE INDEX IF NOT EXISTS idx_runs_created_at  ON runs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status      ON runs (status);
"""

# Colunas que podem ser atualizadas via update_run.
# Allowlist explicita derivada do schema acima: barra qualquer chave fora
# desta lista antes de montar o SET clause, fechando o vetor de SQL injection
# por nome de coluna. A PK `id` fica de fora (e o alvo do WHERE) e os campos
# de identidade (`source`, `source_hash`) nao mudam apos o registro.
_UPDATABLE_COLUMNS = frozenset(
    {
        "title",
        "provider",
        "ai_mode",
        "status",
        "created_at",
        "finished_at",
        "output_dir",
        "analysis_path",
        "markdown_path",
        "duration_seconds",
        "warnings_count",
        "storage_backend",
    }
)

# ---------------------------------------------------------------------------
# RunIndex - gerenciador de contexto
# ---------------------------------------------------------------------------


class RunIndex:
    """
    Gerenciador de contexto para o indice SQLite.

    Uso recomendado:
        with RunIndex() as idx:
            idx.register(run_id, ...)

    Tambem pode ser instanciado sem context manager para uso direto,
    mas _connect() precisa ser chamado manualmente (ou deixado para
    o primeiro metodo que precisar da conexao).
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or resolve_index_path()
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
        self._ensure_schema(conn)
        self._conn = conn
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(_DDL)
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> RunIndex:
        self._connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def register(
        self,
        run_id: str,
        source: str,
        source_hash: str,
        *,
        title: str = "",
        provider: str = "",
        ai_mode: str = "",
        status: str = "completed",
        created_at: str = "",
        finished_at: str = "",
        output_dir: str = "",
        analysis_path: str = "",
        markdown_path: str = "",
        duration_seconds: float = 0.0,
        warnings_count: int = 0,
        storage_backend: str = "filesystem",
    ) -> None:
        """
        Insere ou substitui um run no indice (INSERT OR REPLACE).
        Seguro para ser chamado mais de uma vez com o mesmo run_id
        (idempotente por design).
        """
        conn = self._connect()
        ts = created_at or _iso_now()
        conn.execute(
            """
            INSERT OR REPLACE INTO runs (
                id, source, source_hash, title, provider, ai_mode,
                status, created_at, finished_at, output_dir,
                analysis_path, markdown_path, duration_seconds,
                warnings_count, storage_backend
            ) VALUES (
                :id, :source, :source_hash, :title, :provider, :ai_mode,
                :status, :created_at, :finished_at, :output_dir,
                :analysis_path, :markdown_path, :duration_seconds,
                :warnings_count, :storage_backend
            )
            """,
            {
                "id": run_id,
                "source": source,
                "source_hash": source_hash,
                "title": title,
                "provider": provider,
                "ai_mode": ai_mode,
                "status": status,
                "created_at": ts,
                "finished_at": finished_at,
                "output_dir": output_dir,
                "analysis_path": analysis_path,
                "markdown_path": markdown_path,
                "duration_seconds": duration_seconds,
                "warnings_count": warnings_count,
                "storage_backend": storage_backend,
            },
        )
        conn.commit()

    def update_run(
        self,
        run_id: str,
        **fields: Any,
    ) -> None:
        """
        Atualiza campos especificos de um run existente.
        Usado apos a analise completar para preencher finished_at,
        status, paths, warnings_count etc.

        Cada chave em `fields` e validada contra `_UPDATABLE_COLUMNS`
        antes de compor o SET clause. Qualquer chave fora da allowlist
        levanta ValueError, impedindo que um nome de coluna malicioso
        seja interpolado no SQL.
        """
        if not fields:
            return
        for key in fields:
            if key not in _UPDATABLE_COLUMNS:
                raise ValueError(f"coluna invalida para update: {key}")
        conn = self._connect()
        # Nomes de coluna ja validados pela allowlist acima; valores parametrizados.
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        fields["_id"] = run_id
        conn.execute(
            f"UPDATE runs SET {set_clause} WHERE id = :_id",  # noqa: S608
            fields,
        )
        conn.commit()

    def find_by_hash(self, source_hash: str) -> dict[str, Any] | None:
        """
        Retorna o run mais recente com o source_hash dado, ou None
        se nenhum for encontrado.
        """
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM runs WHERE source_hash = ? ORDER BY created_at DESC LIMIT 1",
            (source_hash,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_runs(
        self,
        limit: int = 20,
        output_dir_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Lista runs ordenados por created_at DESC.

        Args:
            limit: Numero maximo de registros retornados.
            output_dir_filter: Se fornecido, filtra pelo campo output_dir.
        """
        conn = self._connect()
        if output_dir_filter:
            rows = conn.execute(
                "SELECT * FROM runs WHERE output_dir = ? ORDER BY created_at DESC LIMIT ?",
                (output_dir_filter, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Retorna um run pelo ID exato, ou None se nao encontrado."""
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def delete_run(self, run_id: str) -> bool:
        """
        Remove um run do indice pelo ID.

        Retorna True se o run foi encontrado e removido,
        False se o ID nao existia.
        """
        conn = self._connect()
        cursor = conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        conn.commit()
        return cursor.rowcount > 0

    # Alias para manter API uniforme com o design aprovado
    add_run = register
    remove_run = delete_run


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()
