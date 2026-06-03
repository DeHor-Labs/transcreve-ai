"""
Backend de armazenamento S3 / S3-compatible.

Faz upload dos artefatos produzidos pelo pipeline para um bucket S3
usando boto3 com a cadeia de credenciais padrao da AWS (env vars,
~/.aws/credentials, IAM role, etc).

Requer: pip install transcreve-ai[s3]  (boto3>=1.34.0)

Configuracao via env:
    VIDEO_KB_S3_BUCKET     Nome do bucket (obrigatorio)
    VIDEO_KB_S3_PREFIX     Prefixo/pasta dentro do bucket (opcional)
    AWS_ACCESS_KEY_ID      Credencial AWS (ou IAM role implicita)
    AWS_SECRET_ACCESS_KEY  Credencial AWS
    AWS_DEFAULT_REGION     Regiao AWS
    AWS_ENDPOINT_URL       Endpoint customizado (Minio, LocalStack, etc)
"""

from __future__ import annotations

import os
from typing import Any

from ..models import AnalysisResult
from .base import ArtifactPaths, StorageBackend, StorageRef

_BUCKET_ENV = "VIDEO_KB_S3_BUCKET"
_PREFIX_ENV = "VIDEO_KB_S3_PREFIX"


class S3Backend(StorageBackend):
    """
    Backend S3: faz upload de analysis.json e knowledge.md para o bucket
    configurado e retorna URIs s3:// para o indice.

    O upload e idempotente: chaves ja existentes sao sobrescritas, sem
    duplicacao de dados para o mesmo run_id.
    """

    def __init__(self, **opts: Any) -> None:
        self._bucket: str = opts.get("bucket") or os.environ.get(_BUCKET_ENV) or ""
        self._prefix: str = (opts.get("prefix") or os.environ.get(_PREFIX_ENV) or "").rstrip("/")
        self._endpoint_url: str | None = opts.get("endpoint_url") or os.environ.get(
            "AWS_ENDPOINT_URL"
        )
        self._region: str = (
            opts.get("region") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
        )

    # ------------------------------------------------------------------
    # Interface publica
    # ------------------------------------------------------------------

    def save(
        self,
        result: AnalysisResult,
        artifacts: ArtifactPaths,
        **opts: Any,
    ) -> StorageRef:
        """
        Faz upload de analysis.json e knowledge.md para o bucket S3.

        Retorna StorageRef com URIs s3://<bucket>/<chave>.
        """
        client = self._client()
        bucket = self._resolve_bucket()
        prefix = self._build_prefix(result.run_id)

        analysis_key = f"{prefix}/analysis.json"
        markdown_key = f"{prefix}/knowledge.md"

        self._upload(client, bucket, analysis_key, str(artifacts.analysis_json))
        self._upload(client, bucket, markdown_key, str(artifacts.markdown))

        output_uri = f"s3://{bucket}/{prefix}"
        return StorageRef(
            backend="s3",
            output_dir=output_uri,
            analysis_path=f"s3://{bucket}/{analysis_key}",
            markdown_path=f"s3://{bucket}/{markdown_key}",
            extra={
                "bucket": bucket,
                "prefix": prefix,
                "region": self._region,
            },
        )

    def health_check(self) -> None:
        """
        Verifica acesso ao bucket: realiza head_bucket.
        Levanta RuntimeError com mensagem acionavel em caso de falha.
        """
        client = self._client()
        bucket = self._resolve_bucket()
        try:
            client.head_bucket(Bucket=bucket)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"S3Backend: falha ao acessar o bucket '{bucket}'. "
                f"Verifique VIDEO_KB_S3_BUCKET, credenciais AWS e permissoes s3:HeadBucket. "
                f"Erro original: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _client(self) -> Any:
        """Importa boto3 de forma lazy e retorna cliente S3 configurado."""
        try:
            import boto3  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "boto3 nao esta instalado. Instale com: pip install transcreve-ai[s3]"
            ) from exc

        kwargs: dict[str, Any] = {"region_name": self._region}
        if self._endpoint_url:
            kwargs["endpoint_url"] = self._endpoint_url

        try:
            client = boto3.client("s3", **kwargs)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "S3Backend: nao foi possivel criar o cliente boto3. "
                "Verifique as credenciais AWS (env vars, ~/.aws/credentials ou IAM role). "
                f"Erro original: {exc}"
            ) from exc

        return client

    def _resolve_bucket(self) -> str:
        """Retorna o nome do bucket ou levanta erro claro se ausente."""
        if not self._bucket:
            raise RuntimeError(
                f"S3Backend: bucket nao configurado. "
                f"Defina a variavel de ambiente {_BUCKET_ENV} ou passe bucket=<nome> em opts."
            )
        return self._bucket

    def _build_prefix(self, run_id: str) -> str:
        """Monta o prefixo completo para o run: <prefix>/<run_id> ou <run_id>."""
        if self._prefix:
            return f"{self._prefix}/{run_id}"
        return run_id

    def _upload(self, client: Any, bucket: str, key: str, local_path: str) -> None:
        """Faz upload de um arquivo local para S3, com erro acionavel."""
        try:
            client.upload_file(local_path, bucket, key)
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"S3Backend: artefato local nao encontrado: '{local_path}'. "
                "Certifique-se de que o pipeline gravou os artefatos antes de chamar save()."
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"S3Backend: falha ao fazer upload de '{local_path}' "
                f"para s3://{bucket}/{key}. "
                f"Verifique permissoes s3:PutObject no bucket '{bucket}'. "
                f"Erro original: {exc}"
            ) from exc
