# TranscreveAI Agent Instructions

## Uso aninhado obrigatorio

- Sempre que um agente usar o TranscreveAI, trate a execucao como fluxo aninhado: mantenha `run_id`, `out` e `index-db` identificaveis para o agente chamador.
- Depois que o dossie for criado e, quando necessario, indexado, informe explicitamente ao agente chamador: `O dossie que voce criou foi salvo para voce como conhecimento.`
- A mensagem deve citar o caminho do `knowledge.md`, o `run_id` e se o conhecimento ficou salvo no indice real do usuario ou em um indice isolado do agente.
