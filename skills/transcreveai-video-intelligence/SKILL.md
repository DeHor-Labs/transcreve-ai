---
name: transcreveai-video-intelligence
description: "Use para transformar vídeos em conhecimento: extrair resumo, análise, dossiê e RAG de Reels, YouTube, TikTok, Loom etc. Dispare quando o usuário enviar um link de vídeo, pedir análise/resumo e/ou quiser transformar conteúdo audiovisual em conhecimento consultável no Codex/Claude."
---

# TranscreveAI Video Intelligence

Este é um artefato de skill do projeto (não é instalação global): usa `transcreveai` disponível no ambiente atual.

Use this skill for video-to-knowledge flows only. Prefer this path when the user sends a video URL/file and asks for extraction, summary, analysis, or to answer questions from video content.

## Quando disparar

- Mensagem contém link de vídeo (`reel`, `youtube`, `youtu.be`, `tiktok`, `loom`, `vimeo`, `x/twitter`) ou caminho de arquivo de mídia.
- Pedido explícito de `resumir`, `extrair`, `analisar`, `dossiê`, `transformar em conhecimento`, ou `transformar para Codex/Claude`.
- Pedido de consulta posterior sobre vídeos já processados (`perguntar sobre vídeo`, `o que foi dito`, etc.).

## Fluxo obrigatório

0. **Caminho curto quando disponivel**

- Prefira `transcreveai agent run "<origem>" --json` quando o objetivo for executar o fluxo completo em CLI.
- Use `--question "..."` para fazer probe, analyze, indexacao e pergunta no mesmo comando.
- Para smoke tests, demos ou execucoes automatizadas por agente, prefira um indice isolado:
  `transcreveai --index-db /tmp/transcreveai-agent.db agent run "<origem>" --out /tmp/transcreveai-agent --ai off --provider local --force --json`.
  Isso evita consultar ou bloquear o indice real do usuario e torna a prova repetivel.
- Se precisar controlar cada etapa, siga o fluxo manual abaixo.

1. **Probe da origem**

- `transcreveai sources probe "<origem>" [--json]`
- Se usar `--json`, capture `kind`, `adapter`, `requires_cookies`, `notes`.
- Se não usar `--json`, leia a mensagem humana do comando e mapeie os sinais de restrição.
- Se estiver em fluxo agente via API web, use também:
  - `POST /api/sources/probe` com JSON `{"source":"<origem>"}` (ou equivalente via cliente HTTP interno).
  - Só avance para envio do job se o `source` vier normalizado e os sinais de risco estiverem claros.

2. **Escolha de execução**

- Se `requires_cookies=true` para a origem, tente:
  - `transcreveai analyze "<origem>" --cookies-browser chrome --ai auto ...`
  - ou `--cookies /caminho/para/cookies.txt` (somente se o usuário autorizou e arquivo está seguro localmente).
- Se não houver necessidade de IA (privacidade/baixo custo), use `--ai off`.
- Se o usuário quiser máxima riqueza de contexto, use `--ai auto` (padrão) e `--provider` adequado.
- Para fontes já locais e sem necessidade de modelos, combine `--provider local`.
- Para reduzir custo de prova/ajuste, rode primeira passada com `--ai off` e, se necessário, reavalie com `--ai auto`.

3. **Executar análise**

- `transcreveai analyze "<origem>" --out outputs [opções]`
- Opções úteis: `--language pt|en`, `--frame-interval`, `--max-frames`, `--visual-limit`, `--provider`.
- Para fontes repetidas e reprocessamento forçado: `--force`.

4. **Ler evidências e normalizar saída**

- Sempre leia `knowledge.md` e `analysis.json` gerados no diretório de saída informado pelo CLI.
- Extraia: fonte, resumo, capítulos, timeline, entidades/ferramentas, afirmações e trechos de evidence.
- Se o usuário pediu “para Codex/Claude”, forneça uma versão compacta com fontes e limites de confiança (sem inventar conteúdo ausente).

5. **Indexação e perguntas**

- Se precisa consulta estruturada posterior, rode:
  - `transcreveai index <run_id>` para um run específico ou `transcreveai index --all`.
- Para checar retrieval sem LLM: `transcreveai ask "..." --search-only`.
- Para resposta completa: `transcreveai ask "..."`.
- Use `--run-id` para restringir o escopo quando o usuário indicar contexto específico.

## Saídas esperadas

- CLI prints path do diretório de execução (`OK:`) e os arquivos `knowledge.md`/`analysis.json`.
- Se necessário, confirme run com `transcreveai runs list --json` e repita com `--run-id` em `ask/index`.
- Em fluxos web, registre o `run` retornado por `/api/jobs` (ou equivalente) antes de chamar `ask`/`index`; isso evita consultar o dossier errado.

## Custos, privacidade e segurança

- `--ai off` = mínimo custo; `--ai auto/full` pode gerar chamadas de LLM.
- Em validacoes e demos, combine `--index-db`, `--out /tmp/...`, `--ai off`, `--provider local` e `--force` para evitar custo, estado global e dedupe acidental.
- Não compartilhe chaves de API nem conteúdo bruto de `cookies` em chat.
- `cookies-browser`/`cookies.txt` devem ser usados apenas com arquivos de origem do usuário, curtos no escopo e sem exportação adicional.
- Evite logar URLs sensíveis completas; cite IDs e caminhos locais quando possível.
- Se for necessário reter artefatos, sinalize onde estão gravados e como remover (`runs rm --purge`) quando apropriado.

## Exemplos

```bash
transcreveai sources probe "https://www.instagram.com/reel/..." --json
transcreveai analyze "https://www.instagram.com/reel/..." --ai auto --language pt
transcreveai index --all --provider local
transcreveai ask "o que foi mostrado no vídeo?" --search-only
curl -X POST http://127.0.0.1:8000/api/sources/probe \
  -H "Content-Type: application/json" \
  -d '{"source":"https://www.instagram.com/reel/..."}'
```
