# TranscreveAI + LangChain

Demonstração local de RAG: TranscreveAI transforma um vídeo em `knowledge.md`; LangChain divide o dossiê, gera embeddings, recupera até quatro trechos e entrega esses trechos a um modelo para responder. O programa imprime os trechos e o caminho do dossiê para conferência. Índice vetorial em memória, recriado a cada pergunta.

Este exemplo é novo. Não demonstra uso histórico de LangChain, arquitetura multiagente ou serviço de produção.

## Preparação

Python 3.10 ou superior, FFmpeg, TranscreveAI instalado e `OPENAI_API_KEY` válida para embeddings e modelo. A análise pode exigir outras dependências e credenciais descritas no README principal. Chamadas a provedores podem gerar custos; a pergunta e o dossiê são enviados à OpenAI. Use apenas conteúdo que você pode processar.

```bash
cd examples/langchain-transcreveai
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Instale também o TranscreveAI conforme o README principal.
export OPENAI_API_KEY='sua-chave'
python app.py ingest 'URL_OU_CAMINHO_DO_VIDEO' --out ./demo-run
python app.py ask ./demo-run/CAMINHO_MOSTRADO/knowledge.md 'Quais são os pontos principais?'
```

A ingestão imprime o caminho exato do dossiê. O diretório de saída deve estar vazio; o registro do TranscreveAI fica em `demo-run/index.db`, isolado do índice principal, e `--no-index` impede indexação automática. A análise preserva vídeo, áudio e outros artefatos nesse diretório. Proteja ou remova os arquivos após a demonstração. O TranscreveAI pode restringir os diretórios de origem local; configure `VIDEO_KB_ALLOWED_LOCAL_SOURCE_ROOTS` conforme suas regras, se necessário. Se o executável não estiver no PATH, passe `--transcreveai /caminho/para/transcreveai`.

## Como explicar

1. A ingestão produz dossiê com transcrição e análise do vídeo.
2. `RecursiveCharacterTextSplitter` divide o texto em trechos sobrepostos.
3. `OpenAIEmbeddings` converte os trechos e a pergunta em vetores; `InMemoryVectorStore` recupera os mais semelhantes.
4. `ChatOpenAI` responde a partir dos trechos; o programa apresenta os trechos usados para conferência.

A busca sempre devolve os vizinhos mais próximos, mesmo que sejam pouco relevantes. O modelo pode errar ou seguir instruções indevidas presentes no conteúdo; o prompt não garante proteção. Confira respostas e timestamps no material original. Não exponha esta CLI diretamente na internet: não possui autenticação, limites de uso ou isolamento de URLs e arquivos.

## Testes

```bash
python -m pytest -q
```

Os testes usam embeddings e modelo falsos e simulam a chamada ao TranscreveAI. Não usam rede nem medem a qualidade das respostas. Para validar ponta a ponta, execute os comandos de ingestão e pergunta acima com vídeo e credenciais válidas.

Referências: [TranscreveAI](https://github.com/DeHor-Labs/transcreve-ai) e [LangChain](https://docs.langchain.com/oss/python/langchain/overview).
