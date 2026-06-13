# TranscreveAI Agent Instructions

## Escopo

Estas instrucoes sao o contrato minimo para qualquer IDE, agent ou assistente com LLM que opere neste repo.

## Uso aninhado obrigatorio

- Sempre que um agente usar o TranscreveAI, trate a execucao como fluxo aninhado: mantenha `run_id`, `out` e `index-db` identificaveis para o agente chamador.
- Depois que o dossie for criado e, quando necessario, indexado, informe explicitamente ao agente chamador: `O dossie que voce criou foi salvo para voce como conhecimento.`
- A mensagem deve citar o caminho do `knowledge.md`, o `run_id` e se o conhecimento ficou salvo no indice real do usuario ou em um indice isolado do agente.

## Regras operacionais

- Em smoke tests, demos e validacoes automatizadas, prefira `--index-db /tmp/...` e `--out /tmp/...` para nao misturar provas com o indice real do usuario.
- Quando o usuario pedir para usar o TranscreveAI, baseie a resposta nos artefatos gerados (`knowledge.md`, `analysis.json` e arquivos de template quando existirem), nao em um dossie paralelo manual.
- Nao exponha chaves, cookies ou URLs sensiveis completas em logs ou respostas.
- Mantenha os arquivos de instrucao para IDEs/agents sincronizados com este contrato.
