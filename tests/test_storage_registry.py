"""
Testes do registry de backends de storage.

Cobre: load_storage filesystem, ImportError com dica, register_storage,
resolve_storage_name.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class LoadStorageFilesystem(unittest.TestCase):
    def test_filesystem_carrega_sem_dependencias(self) -> None:
        from video_kb.storage import load_storage
        from video_kb.storage.filesystem import FilesystemBackend

        backend = load_storage("filesystem")
        self.assertIsInstance(backend, FilesystemBackend)

    def test_backend_desconhecido_levanta_key_error(self) -> None:
        from video_kb.storage import load_storage

        with self.assertRaises(KeyError) as ctx:
            load_storage("nao_existe_backend")
        self.assertIn("nao_existe_backend", str(ctx.exception))

    def test_key_error_lista_disponiveis(self) -> None:
        from video_kb.storage import load_storage

        with self.assertRaises(KeyError) as ctx:
            load_storage("xpto")
        msg = str(ctx.exception)
        self.assertIn("filesystem", msg)

    def test_backend_sem_dependencia_levanta_import_error_com_dica(self) -> None:
        """
        Simula ImportError ao tentar carregar 'obsidian' sem a lib instalada.
        """

        from video_kb.storage.registry import _REGISTRY

        original = _REGISTRY.get("obsidian")
        # Aponta para modulo inexistente para forcar ImportError
        _REGISTRY["obsidian_fake_test"] = "video_kb.storage._nao_existe:Cls"
        try:
            # Precisamos registrar para que load_storage ache
            from video_kb.storage import load_storage

            with self.assertRaises(ImportError) as ctx:
                load_storage("obsidian_fake_test")
            self.assertIn("obsidian_fake_test", str(ctx.exception))
        finally:
            del _REGISTRY["obsidian_fake_test"]
            if original:
                _REGISTRY["obsidian"] = original

    def test_backend_com_classe_ausente_levanta_import_error(self) -> None:
        """
        Quando o registro aponta para uma classe inexistente, a falha deve ser clara.
        """

        from video_kb.storage.registry import _REGISTRY

        original = _REGISTRY.get("obsidian_fake_test")
        _REGISTRY["obsidian_fake_test"] = "video_kb.storage.obsidian:ClasseInexistente"
        try:
            from video_kb.storage import load_storage

            with self.assertRaises(ImportError) as ctx:
                load_storage("obsidian_fake_test")
            self.assertIn("classe inexistente", str(ctx.exception))
        finally:
            del _REGISTRY["obsidian_fake_test"]
            if original:
                _REGISTRY["obsidian_fake_test"] = original


class RegisterStorageExterno(unittest.TestCase):
    def test_register_storage_adiciona_ao_registry(self) -> None:
        from video_kb.storage import load_storage, register_storage
        from video_kb.storage.filesystem import FilesystemBackend
        from video_kb.storage.registry import _REGISTRY

        # Registra um alias que aponta para FilesystemBackend
        register_storage(
            "test_alias_ext",
            "video_kb.storage.filesystem:FilesystemBackend",
        )
        try:
            backend = load_storage("test_alias_ext")
            self.assertIsInstance(backend, FilesystemBackend)
        finally:
            _REGISTRY.pop("test_alias_ext", None)

    def test_register_sobreescreve_nome_existente(self) -> None:
        from video_kb.storage.registry import _REGISTRY, register_storage

        register_storage("filesystem", "video_kb.storage.filesystem:FilesystemBackend")
        self.assertEqual(_REGISTRY["filesystem"], "video_kb.storage.filesystem:FilesystemBackend")


class ResolveStorageName(unittest.TestCase):
    def test_default_filesystem(self) -> None:
        from video_kb.storage import resolve_storage_name

        env = {k: v for k, v in os.environ.items() if k != "VIDEO_KB_STORAGE"}
        with patch.dict("os.environ", env, clear=True):
            name = resolve_storage_name()
        self.assertEqual(name, "filesystem")

    def test_env_sobreescreve_default(self) -> None:
        from video_kb.storage import resolve_storage_name

        with patch.dict("os.environ", {"VIDEO_KB_STORAGE": "s3"}, clear=False):
            name = resolve_storage_name()
        self.assertEqual(name, "s3")

    def test_cli_flag_sobreescreve_env(self) -> None:
        from video_kb.storage import resolve_storage_name

        with patch.dict("os.environ", {"VIDEO_KB_STORAGE": "s3"}, clear=False):
            name = resolve_storage_name("obsidian")
        self.assertEqual(name, "obsidian")

    def test_cli_flag_none_usa_env(self) -> None:
        from video_kb.storage import resolve_storage_name

        with patch.dict("os.environ", {"VIDEO_KB_STORAGE": "notion"}, clear=False):
            name = resolve_storage_name(None)
        self.assertEqual(name, "notion")


if __name__ == "__main__":
    unittest.main()
