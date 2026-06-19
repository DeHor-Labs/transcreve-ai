# TranscreveAI Agent Instructions

## Escopo

Estas instrucoes sao o contrato minimo para qualquer IDE, agent ou assistente com LLM que opere neste repo.

## Uso aninhado obrigatorio

- Sempre que um agente usar o TranscreveAI, trate a execucao como fluxo aninhado: mantenha `run_id`, `out` e `index-db` identificaveis para o agente chamador.
- Existem dois modos de retencao:
  - **Temporario por padrao**: quando o agente so precisa extrair/resumir/responder a partir de YouTube, Reels, TikTok, arquivo local etc., use `--out` e `--index-db` isolados em `/tmp` ou cache temporario, leia `knowledge.md`/`analysis.json`, responda ao usuario e limpe os artefatos brutos ao final.
  - **Duravel somente quando pedido**: preserve `knowledge.md`, `analysis.json`, frames/audio/source e/ou indexe no indice real apenas quando o usuario pedir salvar, indexar, transformar em conhecimento consultavel, auditar evidencias depois, ou reutilizar o dossie em outro fluxo.
- Se o dossie for preservado ou indexado, informe explicitamente ao agente chamador: `O dossie que voce criou foi salvo para voce como conhecimento.`
- A mensagem de preservacao deve citar o caminho do `knowledge.md`, o `run_id` e se o conhecimento ficou salvo no indice real do usuario ou em um indice isolado do agente.
- Se o dossie foi usado de modo temporario e limpo, nao diga que ficou salvo; informe o `run_id`, que a resposta foi baseada nos artefatos gerados, e que os temporarios foram removidos.

## Regras operacionais

- Em smoke tests, demos e validacoes automatizadas, prefira `--index-db /tmp/...` e `--out /tmp/...` para nao misturar provas com o indice real do usuario.
- Quando o usuario pedir para usar o TranscreveAI, baseie a resposta nos artefatos gerados (`knowledge.md`, `analysis.json` e arquivos de template quando existirem), nao em um dossie paralelo manual.
- Para execucoes temporarias, limpe os artefatos ao final. Um padrao seguro e criar um diretorio dedicado com `mktemp -d`, usar `--out "$TMP/runs"` e `--index-db "$TMP/index.db"`, ler os arquivos necessarios e depois executar `rm -rf "$TMP"`.
- Se a execucao temporaria usou o indice real por engano ou precisou registrar run no indice real, remova o run com `transcreveai runs rm RUN_ID --force` antes de apagar a pasta do run.
- Nao exponha chaves, cookies ou URLs sensiveis completas em logs ou respostas.
- Mantenha os arquivos de instrucao para IDEs/agents sincronizados com este contrato.
