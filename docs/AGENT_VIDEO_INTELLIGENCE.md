# AGENT Video Intelligence (Demo Pack)

## Tese do Produto

`agent video intelligence` no TranscreveAI transforma vídeos curtos e longos em um dossier multimodal pronto para decisão: fala + texto em tela + sinais visuais + contexto temporal.
Em vez de perder contexto em transcrições, o fluxo entrega:

- **Descoberta rápida** do conteúdo importante;
- **Evidência legível** em `knowledge.md`;
- **Consulta conversacional** com `ask` sobre vários vídeos.

Objetivo de demo: provar em 3 minutos que o mesmo conteúdo vira pergunta-resposta útil em menos esforço que assistir manualmente o vídeo inteiro.

## Fluxo de demonstracao: `probe -> analyze -> read dossier -> ask`

> O probe oficial e `transcreveai sources probe`: ele nao baixa o video, apenas identifica a origem, adapter sugerido e avisos provaveis.

Para agentes, o caminho curto e:

```bash
transcreveai agent run "URL_DO_VIDEO" \
  --question "quais ferramentas, passos e riscos aparecem no video?" \
  --json
```

Para demos repetiveis, smoke tests ou uso por agentes em paralelo, isole o indice
SQLite. Assim o mesmo video pode ser testado de novo sem colidir com runs antigos:

```bash
transcreveai --index-db /tmp/transcreveai-demo.db agent run ./demo.mp4 \
  --out /tmp/transcreveai-demo \
  --ai off \
  --provider local \
  --force \
  --json
```

1. **probe**
   Verifica URL/arquivo e viabilidade antes da analise completa.

   ```bash
   transcreveai sources probe "URL_DO_VIDEO" --json
   ```

   Se estiver usando o backend web com `transcreveai serve`, usa também:

   ```bash
   curl -s http://127.0.0.1:8000/api/sources/probe \
     -H "Content-Type: application/json" \
     -d '{"source":"URL_DO_VIDEO"}'
   ```

   Use sempre essa etapa para capturar `requires_cookies`/`notes` e evitar jobs caros no servidor quando a origem falha por autenticação.

2. **analyze**
   Gera artefatos do dossier.

   > Dica de custo: se a fonte vier com `requires_cookies=true` ou risco alto, execute primeiro uma passada sem IA (`--ai off`) e depois refine com `--ai auto` quando o usuário autorizar.

   ```bash
   transcreveai analyze "URL_DO_VIDEO" --ai auto --language pt --frame-interval 4 --max-frames 90 --visual-limit 24
   ```

   Quando a origem foi validada via endpoint, confirme no run o `adapter` sugerido; se o `probe` apontar risco de autenticação, prefira `--cookies-browser chrome` ou `--cookies` apenas com fonte local autorizada.

3. **read dossier**
   Ler o resultado humano:
   ```bash
   RUN_DIR="<diretorio_retornado_em_OK>"
   RUN_ID="$(basename "$RUN_DIR")"
   sed -n "1,140p" "$RUN_DIR/knowledge.md"
   ```

4. **ask**
   Indexar e consultar o índice.
   ```bash
   transcreveai index "$RUN_ID"
   transcreveai ask "Quais decisões foram tomadas e quais ações devo executar?" --run-id "$RUN_ID" --top-k 8
   ```

## Exemplos de prompts para Codex / Claude

### Para Codex (PT-BR)

```text
Você é um analista de conhecimento operacional. Com base no dossiê do run $RUN_ID do TranscreveAI, extraia:
1) resumo executivo de 5 linhas,
2) 5 decisões técnicas,
3) 5 ações acionáveis com prioridade (alta/média/baixa),
4) 3 riscos de execução e como mitigar.
Responda de forma objetiva para time de produto.
```

```text
Use o transcreveai ask no mesmo run para priorizar perguntas:
transcreveai ask "quais etapas foram mostradas no vídeo para configurar o fluxo X?" --run-id "$RUN_ID" --top-k 10
Depois sintetize em uma lista de validação (checklist) curta.
```

### For Claude (EN)

```text
You're helping a product team validate how a feature works. Read the TranscreveAI dossier from run $RUN_ID and return:
- a 1-paragraph summary,
- 3 user-visible claims made in the video,
- 4 concrete verification steps,
- open questions that should be tested in a follow-up.
Keep the tone concise, evidence-first, and reference specific sections/timestamps when available.
```

```text
From this dossier, write a short demo script for a 2-minute internal demo:
- first 20s: framing,
- 20-80s: probe + analyze,
- 80-110s: read dossier,
- 110-120s: ask + decision.
```

## Demo script (Reel, YouTube, TikTok, Loom)

```bash
# 1) Reel
transcreveai analyze "https://www.instagram.com/reel/<slug>" --ai auto --language pt

# 2) YouTube
transcreveai analyze "https://youtu.be/<id>" --ai auto --language en --visual-limit 18

# 3) TikTok
transcreveai analyze "https://www.tiktok.com/@<user>/video/<id>" --ai auto --language pt

# 4) Loom
transcreveai analyze "https://www.loom.com/share/<id>" --ai auto --language en

# Pós-processamento comum
for run in $(ls -1 outputs | tail -n 4); do
  transcreveai index "$run"
  transcreveai ask "Qual é o próximo passo sugerido?" --run-id "$run" --top-k 6
done
```

## Pitch curto

### PT-BR
**“Com Agent Video Intelligence, a transcrição vira inteligência: em minutos o time consulta o que o vídeo mostra, não só o que ele diz. Você analisa, lê o dossier e pergunta o que importa para decisão.”**

### EN
**“Agent Video Intelligence turns video evidence into actionable knowledge: speech, on-screen text, and visuals in one dossier, then query it instantly with one command.”**

## Observações de execução

- Use `transcreveai sources probe` para pre-check sem download; use `--ai off` quando quiser uma analise mais barata sem chamadas de LLM.
- Para smoke tests de agente, use `--index-db /tmp/transcreveai-<nome>.db` e `--out /tmp/transcreveai-<nome>` para manter a prova isolada do indice real do usuario.
- Se repetir o mesmo arquivo/URL no mesmo indice, use `--force`; caso contrario, o dedupe evita reprocessar uma fonte ja concluida.
- Para consultas de produção, rode `transcreveai index "$RUN_ID"` antes de `ask`.
- Evite alterar o README enquanto o fluxo ainda é experimental para reduzir conflitos.
