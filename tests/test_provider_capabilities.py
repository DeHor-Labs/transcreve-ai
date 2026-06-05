"""
Testes de capacidades de cada provider.

Cobre a matriz:
    openai     -> transcribe, vision, synthesize, embed
    local      -> transcribe, embed, synthesize  (SEM vision)
    gemini     -> transcribe, vision, synthesize, embed
    anthropic  -> vision, synthesize  (transcribe so se faster-whisper instalado; SEM embed)

Usa unittest.mock para NAO chamar APIs reais nem baixar modelos.
CapabilityNotSupported deve ser levantado nos casos corretos.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from video_kb.models import SourceMetadata
from video_kb.providers.anthropic_provider import AnthropicProvider
from video_kb.providers.base import AUDIO_CHUNK_LIMIT_BYTES, CapabilityNotSupported
from video_kb.providers.gemini_provider import GeminiProvider
from video_kb.providers.local_provider import LocalProvider
from video_kb.providers.openai_provider import OpenAIProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metadata() -> SourceMetadata:
    return SourceMetadata(source="test.mp4", title="Test")


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


class OpenAICapabilities(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = OpenAIProvider()

    def test_capabilities_completas(self) -> None:
        caps = self.provider.capabilities()
        self.assertIn("transcribe", caps)
        self.assertIn("vision", caps)
        self.assertIn("synthesize", caps)
        self.assertIn("embed", caps)

    def test_transcribe_chama_cliente(self) -> None:
        mock_client = MagicMock()
        resp = MagicMock()
        resp.text = "ola mundo"
        resp.model_dump.return_value = {"text": "ola mundo", "segments": []}
        mock_client.audio.transcriptions.create.return_value = resp
        self.provider._client = mock_client

        # split_audio e importado lazy dentro de _transcribe; patchear no modulo media
        # para interceptar o import lazy corretamente
        with patch("video_kb.media.split_audio", return_value=[Path("/tmp/fake.mp3")]):
            with patch.object(Path, "stat", return_value=MagicMock(st_size=100)):
                with patch.object(Path, "open", MagicMock()):
                    result = self.provider._transcribe(
                        Path("/tmp/fake.mp3"),
                        Path("/tmp/chunks"),
                        None,
                    )
        self.assertIsInstance(result.text, str)

    def test_transcribe_chunks_usam_duracao_real_para_offset(self) -> None:
        chunks = [Path("/tmp/chunk-1.mp3"), Path("/tmp/chunk-2.mp3")]

        with patch("video_kb.media.split_audio", return_value=chunks):
            with patch("video_kb.media.probe_duration", side_effect=[123.0, 45.0]):
                with patch.object(
                    Path,
                    "stat",
                    return_value=MagicMock(st_size=AUDIO_CHUNK_LIMIT_BYTES + 1),
                ):
                    with patch.object(
                        self.provider,
                        "_transcribe_chunk",
                        side_effect=[("parte 1", []), ("parte 2", [])],
                    ) as transcribe_chunk:
                        result = self.provider._transcribe(
                            Path("/tmp/fake.mp3"),
                            Path("/tmp/chunks"),
                            None,
                        )

        offsets = [call.args[1] for call in transcribe_chunk.call_args_list]
        self.assertEqual(offsets, [0.0, 123.0])
        self.assertEqual(result.text, "parte 1\nparte 2")

    def test_transcribe_chunk_retry_reabre_handle(self) -> None:
        mock_client = MagicMock()
        handles = []
        resp = MagicMock()
        resp.text = "ola mundo"
        resp.model_dump.return_value = {"text": "ola mundo", "segments": []}

        def create(**kwargs):
            handles.append(kwargs["file"])
            if len(handles) == 1:
                raise TypeError("timestamp_granularities nao suportado")
            return resp

        mock_client.audio.transcriptions.create.side_effect = create
        self.provider._client = mock_client

        with tempfile.NamedTemporaryFile() as tmp:
            result = self.provider._transcribe_chunk(Path(tmp.name), 0.0, None)

        self.assertEqual(result[0], "ola mundo")
        self.assertEqual(len(handles), 2)
        self.assertIsNot(handles[0], handles[1])
        self.assertTrue(handles[0].closed)
        self.assertTrue(handles[1].closed)

    def test_embed_retorna_lista(self) -> None:
        mock_client = MagicMock()
        embedding_item = MagicMock()
        embedding_item.index = 0
        embedding_item.embedding = [0.1, 0.2, 0.3]
        mock_client.embeddings.create.return_value = MagicMock(data=[embedding_item])
        self.provider._client = mock_client

        result = self.provider._embed(["texto"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], [0.1, 0.2, 0.3])

    def test_complete_publico_retorna_texto(self) -> None:
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "resposta aberta"
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=mock_message)]
        )
        self.provider._client = mock_client

        result = self.provider.complete("pergunta")

        self.assertEqual(result, "resposta aberta")
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        self.assertNotIn("response_format", kwargs)


# ---------------------------------------------------------------------------
# Local
# ---------------------------------------------------------------------------


class LocalCapabilities(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = LocalProvider()

    def test_capabilities_sem_vision(self) -> None:
        caps = self.provider.capabilities()
        self.assertIn("transcribe", caps)
        self.assertIn("embed", caps)
        self.assertIn("synthesize", caps)
        self.assertNotIn("vision", caps)

    def test_describe_frame_levanta_capability_not_supported(self) -> None:
        """describe_frame deve levantar CapabilityNotSupported para o provider local."""
        with self.assertRaises(CapabilityNotSupported) as ctx:
            self.provider.describe_frame(
                image_path=Path("/tmp/frame.jpg"),
                metadata=_make_metadata(),
                timestamp=1.0,
                ocr_text="",
                transcript_context="",
            )
        self.assertEqual(ctx.exception.capability, "vision")

    def test_describe_frame_mensagem_inclui_provider(self) -> None:
        with self.assertRaises(CapabilityNotSupported) as ctx:
            self.provider.describe_frame(
                image_path=Path("/tmp/frame.jpg"),
                metadata=_make_metadata(),
                timestamp=1.0,
                ocr_text="",
                transcript_context="",
            )
        self.assertIn("LocalProvider", str(ctx.exception))

    def test_embed_usa_sentence_transformers(self) -> None:
        mock_model = MagicMock()
        # Simula o retorno de model.encode() sem depender de numpy no venv
        # LocalProvider chama vec.tolist() em cada item do resultado
        fake_vec = MagicMock()
        fake_vec.tolist.return_value = [0.1, 0.2]
        mock_model.encode.return_value = [fake_vec]
        self.provider._embedder = mock_model

        result = self.provider._embed(["frase teste"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], [0.1, 0.2])

    def test_transcribe_chunks_usam_duracao_real_para_offset(self) -> None:
        chunks = [Path("/tmp/local-chunk-1.mp3"), Path("/tmp/local-chunk-2.mp3")]
        self.provider._whisper = MagicMock()

        with patch("video_kb.media.split_audio", return_value=chunks):
            with patch("video_kb.media.probe_duration", side_effect=[77.5, 12.0]):
                with patch.object(
                    Path,
                    "stat",
                    return_value=MagicMock(st_size=AUDIO_CHUNK_LIMIT_BYTES + 1),
                ):
                    with patch.object(
                        self.provider,
                        "_transcribe_chunk",
                        side_effect=[("local 1", []), ("local 2", [])],
                    ) as transcribe_chunk:
                        result = self.provider._transcribe(
                            Path("/tmp/fake.mp3"),
                            Path("/tmp/chunks"),
                            None,
                        )

        offsets = [call.args[2] for call in transcribe_chunk.call_args_list]
        self.assertEqual(offsets, [0.0, 77.5])
        self.assertEqual(result.text, "local 1\nlocal 2")


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------


class GeminiCapabilities(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = GeminiProvider()

    def test_capabilities_completas(self) -> None:
        caps = self.provider.capabilities()
        self.assertIn("transcribe", caps)
        self.assertIn("vision", caps)
        self.assertIn("synthesize", caps)
        self.assertIn("embed", caps)

    def test_describe_frame_usa_genai(self) -> None:
        mock_genai = MagicMock()
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.return_value = MagicMock(text="resposta visual")
        mock_genai.GenerativeModel.return_value = mock_model_instance
        self.provider._genai = mock_genai

        with patch(
            "video_kb.providers.gemini_provider._image_inline_data", return_value=MagicMock()
        ):
            result = self.provider._describe_frame(
                image_path=Path("/tmp/frame.jpg"),
                metadata=_make_metadata(),
                timestamp=5.0,
                ocr_text="ocr aqui",
                transcript_context="contexto",
            )
        self.assertEqual(result, "resposta visual")

    def test_embed_retorna_lista_de_vetores(self) -> None:
        mock_genai = MagicMock()
        mock_genai.embed_content.return_value = {"embedding": [0.5, 0.6, 0.7]}
        self.provider._genai = mock_genai

        result = self.provider._embed(["a", "b"])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], [0.5, 0.6, 0.7])

    def test_complete_publico_retorna_texto(self) -> None:
        mock_genai = MagicMock()
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.return_value = MagicMock(text="resposta gemini")
        mock_genai.GenerativeModel.return_value = mock_model_instance
        self.provider._genai = mock_genai

        result = self.provider.complete("pergunta")

        self.assertEqual(result, "resposta gemini")
        mock_model_instance.generate_content.assert_called_once_with("pergunta")

    def test_transcribe_chunk_limpa_upload_mesmo_quando_generate_content_falha(self) -> None:
        mock_genai = MagicMock()
        mock_audio_file = MagicMock()
        mock_audio_file.name = "files/audio-123"
        mock_genai.upload_file.return_value = mock_audio_file
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.side_effect = RuntimeError("api down")
        mock_genai.GenerativeModel.return_value = mock_model_instance
        self.provider._genai = mock_genai

        with tempfile.NamedTemporaryFile(suffix=".mp3") as tmp:
            with self.assertRaises(RuntimeError):
                self.provider._transcribe_chunk(Path(tmp.name), 0.0, None)

        mock_genai.delete_file.assert_called_once_with("files/audio-123")


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


class AnthropicCapabilities(unittest.TestCase):
    def _make_provider_sem_whisper(self) -> AnthropicProvider:
        """Retorna um AnthropicProvider com faster-whisper simulado como ausente."""
        import video_kb.providers.anthropic_provider as _mod

        provider = AnthropicProvider()
        # Forcamos _FASTER_WHISPER_AVAILABLE = False para este teste
        original = _mod._FASTER_WHISPER_AVAILABLE
        _mod._FASTER_WHISPER_AVAILABLE = False
        self.addCleanup(setattr, _mod, "_FASTER_WHISPER_AVAILABLE", original)
        return provider

    def _make_provider_com_whisper(self) -> AnthropicProvider:
        """Retorna um AnthropicProvider com faster-whisper simulado como presente."""
        import video_kb.providers.anthropic_provider as _mod

        provider = AnthropicProvider()
        original = _mod._FASTER_WHISPER_AVAILABLE
        _mod._FASTER_WHISPER_AVAILABLE = True
        self.addCleanup(setattr, _mod, "_FASTER_WHISPER_AVAILABLE", original)
        return provider

    def test_capabilities_sem_whisper_nao_tem_transcribe(self) -> None:
        provider = self._make_provider_sem_whisper()
        caps = provider.capabilities()
        self.assertIn("vision", caps)
        self.assertIn("synthesize", caps)
        self.assertNotIn("transcribe", caps)
        self.assertNotIn("embed", caps)

    def test_capabilities_com_whisper_tem_transcribe(self) -> None:
        provider = self._make_provider_com_whisper()
        caps = provider.capabilities()
        self.assertIn("transcribe", caps)
        self.assertIn("vision", caps)
        self.assertIn("synthesize", caps)

    def test_embed_levanta_capability_not_supported(self) -> None:
        provider = AnthropicProvider()
        with self.assertRaises(CapabilityNotSupported) as ctx:
            provider.embed(["texto"])
        self.assertEqual(ctx.exception.capability, "embed")

    def test_embed_mensagem_inclui_provider(self) -> None:
        provider = AnthropicProvider()
        with self.assertRaises(CapabilityNotSupported) as ctx:
            provider.embed(["texto"])
        self.assertIn("AnthropicProvider", str(ctx.exception))

    def test_describe_frame_usa_cliente_anthropic(self) -> None:
        provider = AnthropicProvider()
        mock_client = MagicMock()
        mock_block = MagicMock()
        mock_block.text = "descricao do frame"
        mock_client.messages.create.return_value = MagicMock(content=[mock_block])
        provider._client = mock_client

        with patch.object(Path, "read_bytes", return_value=b"fake_image_bytes"):
            result = provider.describe_frame(
                image_path=Path("/tmp/frame.jpg"),
                metadata=_make_metadata(),
                timestamp=2.0,
                ocr_text="texto ocr",
                transcript_context="contexto fala",
            )
        self.assertEqual(result, "descricao do frame")

    def test_complete_publico_retorna_texto(self) -> None:
        provider = AnthropicProvider()
        mock_client = MagicMock()
        mock_block = MagicMock()
        mock_block.text = "resposta anthropic"
        mock_client.messages.create.return_value = MagicMock(content=[mock_block])
        provider._client = mock_client

        result = provider.complete("pergunta")

        self.assertEqual(result, "resposta anthropic")
        mock_client.messages.create.assert_called_once()


# ---------------------------------------------------------------------------
# Matriz cruzada - assegura consistencia via _require()
# ---------------------------------------------------------------------------


class CapabilityRequireGuard(unittest.TestCase):
    """
    Garante que a guard _require() no AIProvider base realmente levanta
    CapabilityNotSupported quando o provider nao declara a capacidade.
    """

    def test_local_transcribe_publico_nao_levanta(self) -> None:
        """transcribe() no LocalProvider nao deve levantar - ele tem a cap."""
        provider = LocalProvider()
        # Nao chama _transcribe de verdade; apenas confirma que _require nao levanta
        # Chamamos capabilities() e verificamos que o guard passaria
        self.assertIn("transcribe", provider.capabilities())

    def test_anthropic_sem_embed_levanta_via_metodo_publico(self) -> None:
        provider = AnthropicProvider()
        with self.assertRaises(CapabilityNotSupported):
            provider.embed(["x"])

    def test_local_complete_sem_implementacao_levanta_via_metodo_publico(self) -> None:
        provider = LocalProvider()
        with self.assertRaises(CapabilityNotSupported):
            provider.complete("pergunta")

    def test_local_sem_vision_levanta_via_metodo_publico(self) -> None:
        provider = LocalProvider()
        with self.assertRaises(CapabilityNotSupported):
            provider.describe_frame(Path("/tmp/f.jpg"), _make_metadata(), 0.0, "", "")


if __name__ == "__main__":
    unittest.main()
