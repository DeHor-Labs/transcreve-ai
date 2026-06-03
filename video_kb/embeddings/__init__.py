"""
video_kb.embeddings - Modulo de busca semantica (RAG) para o transcreve-ai.

API publica:
    EmbeddingChunk      - dataclass de chunk de texto com metadados
    SearchHit           - dataclass de resultado de busca por similaridade
    AskResult           - dataclass de resultado RAG completo
    EmbedNotSupportedError - erro quando provider nao suporta embeddings
    DimMismatchError    - erro de incompatibilidade de dimensoes
    EmbeddingStore      - gerenciador de contexto para tabela embeddings
    chunk_dossier       - divide analysis.json em EmbeddingChunks
    index_run           - indexa um run (chunk + embed + gravar)
    search              - busca chunks por similaridade (sem LLM)
    ask                 - RAG completo (busca + resposta com LLM)

Nota: numpy e importado lazy dentro de EmbeddingStore.search().
      'import video_kb' funciona sem numpy instalado.
      Instale o extra [rag] para usar busca semantica:
          pip install 'transcreve-ai[rag]'
"""

from __future__ import annotations

from .chunker import EmbeddingChunk, chunk_dossier
from .rag import AskResult, ask, index_run, search
from .store import DimMismatchError, EmbeddingStore, SearchHit


class EmbedNotSupportedError(RuntimeError):
    """
    Levantada quando o provider configurado nao suporta embeddings.

    Providers com suporte a embed: openai, local, gemini.
    Anthropic nao suporta embeddings.

    Para usar busca semantica, configure um provider compativel:
        transcreveai index --all --provider openai
        transcreveai index --all --provider local   (gratuito, offline)
        transcreveai index --all --provider gemini
    """

    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name
        super().__init__(
            f"Provider '{provider_name}' nao suporta embeddings. "
            "Use --provider openai, local ou gemini. "
            "Para uso offline e gratuito, use --provider local."
        )


__all__ = [
    "AskResult",
    "DimMismatchError",
    "EmbedNotSupportedError",
    "EmbeddingChunk",
    "EmbeddingStore",
    "SearchHit",
    "ask",
    "chunk_dossier",
    "index_run",
    "search",
]
