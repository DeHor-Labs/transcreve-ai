"""
Backend de armazenamento Notion.

Cria uma pagina no Notion com o resumo e capitulos do KnowledgeSynthesis.
Requer: pip install transcreve-ai[notion]  (notion-client>=2.0.0)

Configuracao via env:
    NOTION_API_KEY        Token de integracao do Notion (obrigatorio)
    NOTION_DATABASE_ID    ID do banco de dados destino (obrigatorio)
"""

from __future__ import annotations

import os
from typing import Any

from ..models import AnalysisResult
from .base import ArtifactPaths, StorageBackend, StorageRef

_MISSING_SDK_MSG = (
    "O pacote 'notion-client' nao esta instalado. Instale com: pip install transcreve-ai[notion]"
)


def _require_notion_client() -> Any:
    """Importa notion-client ou levanta ImportError claro."""
    try:
        import notion_client  # type: ignore[import-untyped]

        return notion_client
    except ImportError as exc:
        raise ImportError(_MISSING_SDK_MSG) from exc


def _text_block(content: str) -> dict[str, Any]:
    """Bloco paragrafo simples com texto plano."""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": content[:2000]}}]},
    }


def _heading2_block(content: str) -> dict[str, Any]:
    """Bloco heading_2."""
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": content[:2000]}}]},
    }


def _bulleted_block(content: str) -> dict[str, Any]:
    """Bloco bulleted_list_item."""
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [{"type": "text", "text": {"content": content[:2000]}}]
        },
    }


def _divider_block() -> dict[str, Any]:
    return {"object": "block", "type": "divider", "divider": {}}


def _build_blocks(result: AnalysisResult) -> list[dict[str, Any]]:
    """Converte AnalysisResult em lista de blocos Notion."""
    s = result.synthesis
    meta = result.metadata
    blocks: list[dict[str, Any]] = []

    # Cabecalho com metadados
    if meta.webpage_url:
        blocks.append(_text_block(f"Fonte: {meta.webpage_url}"))
    if meta.uploader or meta.channel:
        canal = meta.uploader or meta.channel
        blocks.append(_text_block(f"Canal: {canal}"))
    if meta.duration:
        minutos = int(meta.duration // 60)
        segundos = int(meta.duration % 60)
        blocks.append(_text_block(f"Duracao: {minutos}m{segundos:02d}s"))
    if meta.upload_date:
        blocks.append(_text_block(f"Data de upload: {meta.upload_date}"))

    blocks.append(_divider_block())

    # Resumo
    if s.summary:
        blocks.append(_heading2_block("Resumo"))
        # Quebra em paragrafos de 2000 chars para respeitar limite da API
        texto = s.summary
        while texto:
            bloco, texto = texto[:2000], texto[2000:]
            blocks.append(_text_block(bloco))

    # Capitulos
    if s.chapters:
        blocks.append(_divider_block())
        blocks.append(_heading2_block("Capitulos"))
        for cap in s.chapters:
            titulo = cap.get("title") or cap.get("nome") or str(cap)
            inicio = cap.get("start") or cap.get("inicio") or ""
            label = f"{inicio}  {titulo}".strip() if inicio else str(titulo)
            blocks.append(_bulleted_block(label))

    # Entidades
    if s.entities:
        blocks.append(_divider_block())
        blocks.append(_heading2_block("Entidades mencionadas"))
        for ent in s.entities:
            blocks.append(_bulleted_block(ent))

    # Ferramentas / Produtos
    if s.tools_or_products:
        blocks.append(_divider_block())
        blocks.append(_heading2_block("Ferramentas e Produtos"))
        for item in s.tools_or_products:
            blocks.append(_bulleted_block(item))

    # Afirmacoes importantes
    if s.claims:
        blocks.append(_divider_block())
        blocks.append(_heading2_block("Afirmacoes importantes"))
        for c in s.claims:
            blocks.append(_bulleted_block(c))

    # Acoes
    if s.action_items:
        blocks.append(_divider_block())
        blocks.append(_heading2_block("Acoes"))
        for a in s.action_items:
            blocks.append(_bulleted_block(a))

    # Perguntas
    if s.questions:
        blocks.append(_divider_block())
        blocks.append(_heading2_block("Perguntas levantadas"))
        for q in s.questions:
            blocks.append(_bulleted_block(q))

    # Rodape tecnico
    blocks.append(_divider_block())
    blocks.append(_text_block(f"run_id: {result.run_id}"))

    return blocks


class NotionBackend(StorageBackend):
    """
    Backend Notion: cria uma pagina no banco de dados configurado.

    Cada chamada a save() cria UMA pagina nova. A API do Notion nao
    oferece busca por campo arbitrario de forma gratuita, portanto
    a idempotencia por run_id nao e garantida sem um indice externo.

    Configuracao obrigatoria (env ou opts):
        NOTION_API_KEY       Token de integracao interna do Notion
        NOTION_DATABASE_ID   ID do banco de dados destino

    A integracao deve ter permissao de "Inserir conteudo" no banco.
    Adicione a integracao ao banco em: ... -> Conectar a -> <nome da integracao>
    """

    def __init__(self, **opts: Any) -> None:
        self._api_key: str = opts.get("api_key") or os.environ.get("NOTION_API_KEY") or ""
        self._database_id: str = (
            opts.get("database_id") or os.environ.get("NOTION_DATABASE_ID") or ""
        )

    def _validate_credentials(self) -> None:
        erros: list[str] = []
        if not self._api_key:
            erros.append(
                "NOTION_API_KEY nao definida. "
                "Gere um token em https://www.notion.so/my-integrations "
                "e exporte: export NOTION_API_KEY=secret_..."
            )
        if not self._database_id:
            erros.append(
                "NOTION_DATABASE_ID nao definido. "
                "Abra o banco no Notion, clique em '...' -> 'Copiar link', "
                "e use o UUID do link: export NOTION_DATABASE_ID=<uuid>"
            )
        if erros:
            raise RuntimeError("\n".join(erros))

    def health_check(self) -> None:
        """Verifica SDK e credenciais sem criar pagina."""
        nc = _require_notion_client()
        self._validate_credentials()
        client = nc.Client(auth=self._api_key)
        try:
            client.databases.retrieve(database_id=self._database_id)
        except Exception as exc:
            raise RuntimeError(
                f"Falha ao conectar ao banco Notion (id={self._database_id}): {exc}\n"
                "Verifique se a integracao foi adicionada ao banco de dados no Notion."
            ) from exc

    def save(
        self,
        result: AnalysisResult,
        artifacts: ArtifactPaths,
        **opts: Any,
    ) -> StorageRef:
        """
        Cria uma pagina no Notion com o conteudo de AnalysisResult.

        Retorna StorageRef com a URL da pagina criada em extra['page_url'].
        Levanta ImportError se notion-client nao estiver instalado.
        Levanta RuntimeError se credenciais estiverem ausentes ou invalidas.
        """
        nc = _require_notion_client()

        # Permite sobrescrever credenciais por chamada
        api_key = opts.get("api_key") or self._api_key
        database_id = opts.get("database_id") or self._database_id

        # Valida usando os valores efetivos desta chamada
        erros: list[str] = []
        if not api_key:
            erros.append(
                "NOTION_API_KEY nao definida. "
                "Gere um token em https://www.notion.so/my-integrations "
                "e exporte: export NOTION_API_KEY=secret_..."
            )
        if not database_id:
            erros.append(
                "NOTION_DATABASE_ID nao definido. "
                "Abra o banco no Notion, clique em '...' -> 'Copiar link', "
                "e use o UUID do link: export NOTION_DATABASE_ID=<uuid>"
            )
        if erros:
            raise RuntimeError("\n".join(erros))

        client = nc.Client(auth=api_key)

        titulo = result.metadata.title or result.source or result.run_id
        blocks = _build_blocks(result)

        # A API do Notion aceita no maximo 100 blocos por request de criacao
        MAX_BLOCKS_CREATE = 100
        initial_blocks = blocks[:MAX_BLOCKS_CREATE]
        extra_blocks = blocks[MAX_BLOCKS_CREATE:]

        try:
            page = client.pages.create(
                parent={"database_id": database_id},
                properties={
                    "title": {"title": [{"type": "text", "text": {"content": titulo[:2000]}}]}
                },
                children=initial_blocks,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Falha ao criar pagina no Notion: {exc}\n"
                "Verifique permissoes da integracao e o NOTION_DATABASE_ID."
            ) from exc

        page_id: str = page["id"]

        # Appenda blocos restantes em lotes de 100
        if extra_blocks:
            for i in range(0, len(extra_blocks), MAX_BLOCKS_CREATE):
                lote = extra_blocks[i : i + MAX_BLOCKS_CREATE]
                try:
                    client.blocks.children.append(block_id=page_id, children=lote)
                except Exception as exc:  # noqa: BLE001
                    import warnings

                    warnings.warn(
                        f"Falha ao adicionar blocos extras a pagina Notion {page_id}: {exc}",
                        stacklevel=2,
                    )
                    break

        page_url: str = page.get("url", "")

        return StorageRef(
            backend="notion",
            output_dir=page_url,
            analysis_path=str(artifacts.analysis_json),
            markdown_path=str(artifacts.markdown),
            extra={
                "page_id": page_id,
                "page_url": page_url,
                "database_id": database_id,
            },
        )
