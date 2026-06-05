"""
Testes para video_kb.providers.registry.

Cobre:
- Lista de providers registrados (openai, local, gemini, anthropic)
- get_provider("openai") instancia corretamente via load_provider
- Nome invalido levanta KeyError com mensagem clara
- Import lazy: listar o registry NAO importa libs opcionais
"""

from __future__ import annotations

import importlib
import sys
import unittest
import warnings
from types import SimpleNamespace
from unittest.mock import patch

from video_kb.providers.registry import (
    _DEFAULT_PROVIDER,
    _REGISTRY,
    load_provider,
    resolve_provider_name,
)


class RegistryListaProviders(unittest.TestCase):
    """O registry deve conhecer os quatro providers canônicos."""

    def test_openai_registrado(self) -> None:
        self.assertIn("openai", _REGISTRY)

    def test_local_registrado(self) -> None:
        self.assertIn("local", _REGISTRY)

    def test_gemini_registrado(self) -> None:
        self.assertIn("gemini", _REGISTRY)

    def test_anthropic_registrado(self) -> None:
        self.assertIn("anthropic", _REGISTRY)

    def test_default_e_openai(self) -> None:
        self.assertEqual(_DEFAULT_PROVIDER, "openai")


class RegistryGetProvider(unittest.TestCase):
    """load_provider deve instanciar OpenAIProvider sem chamar rede."""

    def test_get_openai_retorna_instancia(self) -> None:
        # A lib openai esta instalada no .venv do projeto - import real e ok aqui
        provider = load_provider("openai")
        from video_kb.providers.base import AIProvider

        self.assertIsInstance(provider, AIProvider)

    def test_get_openai_tem_capabilities(self) -> None:
        provider = load_provider("openai")
        caps = provider.capabilities()
        self.assertIn("transcribe", caps)
        self.assertIn("vision", caps)
        self.assertIn("synthesize", caps)
        self.assertIn("embed", caps)

    def test_openai_recebe_overrides_de_modelo(self) -> None:
        provider = load_provider(
            "openai",
            vision_model="gpt-vision-custom",
            transcribe_model="whisper-custom",
            language="pt",
        )

        self.assertEqual(provider.vision_model, "gpt-vision-custom")
        self.assertEqual(provider.transcribe_model, "whisper-custom")
        self.assertEqual(provider.language, "pt")

    def test_local_recebe_override_de_whisper(self) -> None:
        provider = load_provider("local", transcribe_model="small")

        self.assertEqual(provider.whisper_model, "small")

    def test_classe_registrada_inexistente_levanta_importerror_claro(self) -> None:
        with patch.dict(
            _REGISTRY,
            {"quebrado": "video_kb.providers.local_provider:ProviderQueNaoExiste"},
        ):
            with self.assertRaises(ImportError) as ctx:
                load_provider("quebrado")

        mensagem = str(ctx.exception)
        self.assertIn("ProviderQueNaoExiste", mensagem)
        self.assertIn("video_kb.providers.local_provider", mensagem)

    def test_referencia_sem_classe_levanta_importerror_claro(self) -> None:
        with patch.dict(_REGISTRY, {"quebrado": "video_kb.providers.local_provider"}):
            with self.assertRaises(ImportError) as ctx:
                load_provider("quebrado")

        mensagem = str(ctx.exception)
        self.assertIn("quebrado", mensagem)
        self.assertIn("modulo:Classe", mensagem)


class RegistryNomeInvalido(unittest.TestCase):
    """Provider desconhecido deve levantar KeyError com mensagem descritiva."""

    def test_nome_invalido_levanta_keyerror(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            load_provider("nao_existe")
        mensagem = str(ctx.exception)
        self.assertIn("nao_existe", mensagem)
        # A mensagem deve listar os providers disponiveis
        self.assertIn("openai", mensagem)

    def test_mensagem_lista_disponiveis(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            load_provider("fantasma")
        mensagem = str(ctx.exception)
        for nome in ("openai", "local", "gemini", "anthropic"):
            self.assertIn(nome, mensagem)


class RegistryImportLazy(unittest.TestCase):
    """Listar o registry NAO deve exigir que libs opcionais estejam instaladas."""

    def test_listar_registry_sem_google_generativeai(self) -> None:
        """Simula ausência da lib google-generativeai; listar o registry nao deve falhar."""
        # Remove o modulo do sys.modules para simular nao-instalado
        modulos_backup = {}
        for key in list(sys.modules.keys()):
            if "google" in key and "generativeai" in key:
                modulos_backup[key] = sys.modules.pop(key)
        try:
            # A simples iteracao sobre _REGISTRY nao deve levantar ImportError
            nomes = list(_REGISTRY.keys())
            self.assertIn("gemini", nomes)
        finally:
            sys.modules.update(modulos_backup)

    def test_listar_registry_sem_anthropic(self) -> None:
        """Simula ausência da lib anthropic; listar o registry nao deve falhar."""
        modulos_backup = {}
        for key in list(sys.modules.keys()):
            if key == "anthropic" or key.startswith("anthropic."):
                modulos_backup[key] = sys.modules.pop(key)
        try:
            nomes = list(_REGISTRY.keys())
            self.assertIn("anthropic", nomes)
        finally:
            sys.modules.update(modulos_backup)

    def test_listar_registry_sem_faster_whisper(self) -> None:
        """Simula ausência da lib faster-whisper; listar o registry nao deve falhar."""
        modulos_backup = {}
        for key in list(sys.modules.keys()):
            if "faster_whisper" in key:
                modulos_backup[key] = sys.modules.pop(key)
        try:
            nomes = list(_REGISTRY.keys())
            self.assertIn("local", nomes)
        finally:
            sys.modules.update(modulos_backup)


class RegistryResolveProviderName(unittest.TestCase):
    """resolve_provider_name segue precedencia: CLI > env > default."""

    def test_cli_tem_prioridade_sobre_env(self) -> None:
        with patch.dict("os.environ", {"VIDEO_KB_PROVIDER": "gemini"}):
            self.assertEqual(resolve_provider_name("anthropic"), "anthropic")

    def test_env_tem_prioridade_sobre_default(self) -> None:
        with patch.dict("os.environ", {"VIDEO_KB_PROVIDER": "local"}, clear=False):
            self.assertEqual(resolve_provider_name(None), "local")

    def test_default_e_openai_sem_env(self) -> None:
        env_sem_provider = {
            k: v for k, v in __import__("os").environ.items() if k != "VIDEO_KB_PROVIDER"
        }
        with patch.dict("os.environ", env_sem_provider, clear=True):
            self.assertEqual(resolve_provider_name(None), "openai")

    def test_string_vazia_cai_no_default(self) -> None:
        env_sem_provider = {
            k: v for k, v in __import__("os").environ.items() if k != "VIDEO_KB_PROVIDER"
        }
        with patch.dict("os.environ", env_sem_provider, clear=True):
            # string vazia e falsy, deve cair no default
            self.assertEqual(resolve_provider_name(""), "openai")


class RegistryEntryPointWarnings(unittest.TestCase):
    """A inicializacao do package de providers deve avisar falhas de entry points."""

    def test_falha_no_entry_points_gera_warning(self) -> None:
        import video_kb.providers as providers_pkg

        with patch(
            "video_kb.providers.importlib.metadata.entry_points",
            side_effect=RuntimeError("entry_points indisponivel"),
        ):
            with warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always")
                importlib.reload(providers_pkg)

        self.assertTrue(
            any(
                "nao foi possivel carregar entry points" in str(item.message).lower()
                for item in captured
            ),
            "Esperado warning explícito quando entry_points falha.",
        )

    def test_entry_point_invalido_gera_warning(self) -> None:
        fake_entry = SimpleNamespace(name="xpto", value="provider")

        import video_kb.providers as providers_pkg

        with patch(
            "video_kb.providers.importlib.metadata.entry_points",
            return_value=[fake_entry],
        ):
            with warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always")
                importlib.reload(providers_pkg)

        mensagem = " ".join(str(item.message) for item in captured)
        self.assertIn("falha", mensagem.lower())
        self.assertIn("referencia de classe", mensagem)


if __name__ == "__main__":
    unittest.main()
