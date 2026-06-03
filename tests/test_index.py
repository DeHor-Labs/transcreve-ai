"""
Testes unitarios do modulo video_kb/index.py.

Cobre: schema, register, find_by_hash, list_runs, get_run, delete_run,
DuplicateRunError, degradacao gracil e resolucao de caminho.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ResolveIndexPath(unittest.TestCase):
    def test_default_usa_home_transcreveai(self) -> None:
        from video_kb.index import resolve_index_path

        env = {k: v for k, v in os.environ.items() if k != "VIDEO_KB_INDEX_DB"}
        with patch.dict("os.environ", env, clear=True):
            path = resolve_index_path()
        self.assertTrue(str(path).endswith("index.db"))
        self.assertIn(".transcreveai", str(path))

    def test_env_sobreescreve_default(self) -> None:
        from video_kb.index import resolve_index_path

        with patch.dict("os.environ", {"VIDEO_KB_INDEX_DB": "/tmp/meu.db"}, clear=False):
            path = resolve_index_path()
        self.assertTrue(str(path).endswith("meu.db"))

    def test_cli_flag_sobreescreve_env(self) -> None:
        from video_kb.index import resolve_index_path

        with patch.dict("os.environ", {"VIDEO_KB_INDEX_DB": "/tmp/env.db"}, clear=False):
            path = resolve_index_path("/tmp/cli.db")
        # cli_flag tem prioridade; env.db nao deve aparecer no caminho
        self.assertTrue(str(path).endswith("cli.db"))
        self.assertNotIn("env.db", str(path))


class RunIndexSchema(unittest.TestCase):
    def _make_index(self):  # type: ignore[return]
        from video_kb.index import RunIndex

        tmp = tempfile.mktemp(suffix=".db")
        return RunIndex(Path(tmp))

    def test_connect_cria_db(self) -> None:
        from video_kb.index import RunIndex

        with tempfile.TemporaryDirectory() as d:
            db_path = Path(d) / "sub" / "index.db"
            with RunIndex(db_path) as idx:
                # so de conectar ja deve criar o arquivo
                runs = idx.list_runs()
            self.assertTrue(db_path.exists())
            self.assertEqual(runs, [])

    def test_schema_cria_tabela_runs(self) -> None:
        import sqlite3

        from video_kb.index import RunIndex

        with tempfile.TemporaryDirectory() as d:
            db_path = Path(d) / "index.db"
            with RunIndex(db_path):
                pass
            conn = sqlite3.connect(str(db_path))
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            conn.close()
        self.assertIn("runs", tables)


class RunIndexCRUD(unittest.TestCase):
    def setUp(self) -> None:
        from video_kb.index import RunIndex

        self._tmp = tempfile.mkdtemp()
        self._db = Path(self._tmp) / "index.db"
        self._idx = RunIndex(self._db)
        self._idx._connect()

    def tearDown(self) -> None:
        self._idx.close()

    def _register(self, run_id: str = "run-001", source_hash: str = "abc123") -> None:
        self._idx.register(
            run_id=run_id,
            source="https://example.com/video",
            source_hash=source_hash,
            title="Video Teste",
            provider="openai",
            ai_mode="auto",
            status="completed",
            output_dir="/tmp/outputs/run-001",
            analysis_path="/tmp/outputs/run-001/analysis.json",
            markdown_path="/tmp/outputs/run-001/knowledge.md",
            duration_seconds=120.5,
            warnings_count=0,
            storage_backend="filesystem",
        )

    def test_register_insere_run(self) -> None:
        self._register()
        runs = self._idx.list_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], "run-001")

    def test_register_idempotente(self) -> None:
        self._register()
        self._register()  # segunda chamada nao deve duplicar
        runs = self._idx.list_runs()
        self.assertEqual(len(runs), 1)

    def test_find_by_hash_retorna_run(self) -> None:
        self._register(source_hash="hash-xyz")
        found = self._idx.find_by_hash("hash-xyz")
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found["id"], "run-001")

    def test_find_by_hash_retorna_none_quando_ausente(self) -> None:
        result = self._idx.find_by_hash("nao-existe")
        self.assertIsNone(result)

    def test_get_run_retorna_run(self) -> None:
        self._register()
        run = self._idx.get_run("run-001")
        self.assertIsNotNone(run)
        assert run is not None
        self.assertEqual(run["title"], "Video Teste")

    def test_get_run_retorna_none_quando_ausente(self) -> None:
        result = self._idx.get_run("nao-existe")
        self.assertIsNone(result)

    def test_delete_run_remove(self) -> None:
        self._register()
        removed = self._idx.delete_run("run-001")
        self.assertTrue(removed)
        self.assertIsNone(self._idx.get_run("run-001"))

    def test_delete_run_retorna_false_quando_ausente(self) -> None:
        removed = self._idx.delete_run("nao-existe")
        self.assertFalse(removed)

    def test_update_run_altera_campos(self) -> None:
        self._register(run_id="run-upd")
        self._idx.update_run("run-upd", status="failed", warnings_count=3)
        run = self._idx.get_run("run-upd")
        assert run is not None
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["warnings_count"], 3)

    def test_update_run_coluna_invalida_levanta(self) -> None:
        # Coluna fora da allowlist deve ser rejeitada antes de tocar o SQL.
        self._register(run_id="run-bad")
        with self.assertRaises(ValueError):
            self._idx.update_run("run-bad", coluna_inexistente="x")

    def test_update_run_coluna_maliciosa_levanta(self) -> None:
        # Vetor de SQL injection por nome de coluna fica fechado: a chave
        # maliciosa nao esta na allowlist, entao update_run levanta ValueError
        # em vez de interpolar o payload no SET clause.
        self._register(run_id="run-evil")
        payload = "status = 'pwned' WHERE 1=1; DROP TABLE runs; --"
        with self.assertRaises(ValueError):
            self._idx.update_run("run-evil", **{payload: "x"})
        # tabela intacta e dado original preservado
        run = self._idx.get_run("run-evil")
        assert run is not None
        self.assertEqual(run["status"], "completed")

    def test_list_runs_limit(self) -> None:
        for i in range(5):
            self._register(run_id=f"run-{i:03d}", source_hash=f"hash-{i}")
        runs = self._idx.list_runs(limit=3)
        self.assertEqual(len(runs), 3)

    def test_list_runs_filter_output_dir(self) -> None:
        self._register(run_id="run-a", source_hash="ha")
        self._idx.register(
            run_id="run-b",
            source="src",
            source_hash="hb",
            output_dir="/outro/dir",
        )
        runs = self._idx.list_runs(output_dir_filter="/tmp/outputs/run-001")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], "run-a")

    def test_alias_add_run(self) -> None:
        # add_run e alias de register
        self._idx.add_run(
            run_id="run-alias",
            source="x",
            source_hash="alias-hash",
        )
        self.assertIsNotNone(self._idx.get_run("run-alias"))

    def test_alias_remove_run(self) -> None:
        self._register(run_id="run-rem")
        result = self._idx.remove_run("run-rem")
        self.assertTrue(result)


class DuplicateRunErrorTest(unittest.TestCase):
    def test_carrega_existing(self) -> None:
        from video_kb.index import DuplicateRunError

        existing = {"id": "run-123", "output_dir": "/tmp/run-123"}
        exc = DuplicateRunError(existing)
        self.assertEqual(exc.existing["id"], "run-123")
        self.assertIn("run-123", str(exc))

    def test_e_runtime_error(self) -> None:
        from video_kb.index import DuplicateRunError

        exc = DuplicateRunError({"id": "x", "output_dir": "/tmp"})
        self.assertIsInstance(exc, RuntimeError)


class DegradacaoGracil(unittest.TestCase):
    """RunIndex nao deve levantar excecao ao usar context manager mesmo com DB invalido."""

    def test_db_em_dir_inexistente_cria_dir(self) -> None:
        from video_kb.index import RunIndex

        with tempfile.TemporaryDirectory() as d:
            db_path = Path(d) / "a" / "b" / "c" / "index.db"
            with RunIndex(db_path) as idx:
                runs = idx.list_runs()
            self.assertEqual(runs, [])
            self.assertTrue(db_path.exists())

    def test_context_manager_fecha_conexao(self) -> None:
        from video_kb.index import RunIndex

        with tempfile.TemporaryDirectory() as d:
            db_path = Path(d) / "index.db"
            idx = RunIndex(db_path)
            with idx:
                idx.register(run_id="r1", source="s", source_hash="h1")
            # apos __exit__, _conn deve ser None
            self.assertIsNone(idx._conn)


if __name__ == "__main__":
    unittest.main()
