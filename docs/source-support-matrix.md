# Matriz objetiva de suporte de fonte de vídeo

Documento para decidir rapidamente a estratégia de ingestão no MVP e o plano de fallback por fonte.

**Legenda de status do MVP**

- **✅ MVP**: fluxo atual de produção funciona de forma estável.
- **🟡 MVP com ressalvas**: funcionável, porém frágil (auth/rate limits/extrator).
- **⚠️ MVP não-verificado**: não testado com frequência no pipeline atual.

## Protocolo de pré-checagem e custo

Antes de `analyze`, rode `probe` para reduzir custo e reduzir retries:

- CLI: `transcreveai sources probe URL_DA_FONTE`
- API: `POST /api/sources/probe` com body `{ "source": "URL_DA_FONTE" }`

Se `requires_cookies=true`, priorize um run `--ai off` para validar extração e só depois habilite IA.
- Se o resultado de `probe` retornar `notes` com risco alto (login/session, anti-bot, URL temporária), considere `--cookies-browser chrome` (ou `--cookies`) e `--max-frames` reduzido no primeiro teste.
- Para fontes de maior risco, mantenha `--out` explícito para facilitar reprovação rápida e comparação de resultados.

## Matriz (YouTube, Instagram/Reels, TikTok, X/Twitter, LinkedIn, Vimeo, Loom, Google Drive público, Dropbox/direct file, Reddit, Twitch, local files, MP4/MOV/M3U8)

| Fonte | Estratégia primária | Fallback (yt-dlp / direct / cookies / captions) | Riscos | Smoke recomendado | Status MVP |
|---|---|---|---|---|---|
| YouTube | `yt-dlp` com `--format` padrão e deduplicação por hash de URL. | Se falhar por região ou bloqueio leve: ajustar `--format` (`bestvideo*+bestaudio/best`) e repetir. Para conteúdo bloqueado por sessão, usar `--cookies-browser`/`--cookies`. Legendas: usar subtítulos quando disponíveis (`--write-subs/--write-auto-subs` em validação manual). | Quotas, bloqueios temporários, alterações de layout de páginas e IDs inválidos para lives/shorts. | `transcreveai analyze "https://youtu.be/..." --ai off --max-frames 20` | ✅ MVP |
| Instagram / Reels | `yt-dlp` diretamente da URL do reel. | Falhas de parser/carregamento: coletar URL de origem (`?igsh=...` limpo), reprocessar com cookies reais do navegador (`--cookies-browser chrome`), manter fallback para arquivo local se disponibilizado pelo usuário. Legendas: normalmente ausentes; não há uso atual no pipeline. | Forte bloqueio anti-bot e mudanças de login, conteúdo privado/age-limited, instabilidade em contas com segurança agressiva. | `transcreveai analyze "https://www.instagram.com/reel/..." --cookies-browser chrome --ai off --max-frames 20` | 🟡 MVP com ressalvas |
| TikTok | `yt-dlp` para URL pública e URLs canônicas. | Se travar em redirecionamento/método de embed: testar link canônico do vídeo; usar captura por arquivo compartilhado quando a plataforma oferece opção de download; legendas opcionais geralmente fracas (`--write-auto-subs`) em validação manual. | Bot protection, variação de URL short links, ausência de caption em vídeos antigos. | `transcreveai analyze "https://www.tiktok.com/@.../video/..." --ai off --max-frames 20` | 🟡 MVP com ressalvas |
| X / Twitter | `yt-dlp` para URL do post com vídeo. | Se autenticação necessária: usar `--cookies-browser` e reprocessar com cookie atualizado. Falha persistente: baixar vídeo para arquivo local (quando compartilhamento permite) e reprocessar via fonte local. Legendas: raramente confiáveis, usar transcript por áudio como fallback. | Mudanças frequentes de front-end/API, bloqueio por bot/proxy/rate limit, vídeos truncados em threads longas. | `transcreveai analyze "https://x.com/.../status/..." --cookies-browser chrome --ai off --max-frames 20` | 🟡 MVP com ressalvas |
| LinkedIn | `yt-dlp` para vídeo público em publicação. | Se cair para conteúdo autenticado: usar `--cookies-browser` ou `--cookies` atualizados. Para posts corporativos, tentar captura da versão "downloadable" ou vídeo local quando disponível. Legendas: `yt-dlp` pode extrair legível apenas em posts com closed captions; caso contrário transcript por áudio. | Login obrigatório em muitas organizações, cookies expirados, metadados incompletos. | `transcreveai analyze "https://www.linkedin.com/posts/..." --cookies-browser chrome --ai off --max-frames 20` | 🟡 MVP com ressalvas |
| Vimeo | `yt-dlp` com selector de formato padrão. | Se falhar em assets protegidos: validar link direto de download (se público) e subir como arquivo local. Legendas: usar fluxo de captions se disponíveis, caso contrário transcript por áudio. | Vídeos privados, expiração de link e alterações no player de embeds. | `transcreveai analyze "https://vimeo.com/..." --ai off --max-frames 20` | ✅ MVP |
| Loom | `yt-dlp` em URL compartilhada pública do Loom. | Se o share quebrar embed: usar link de download direto (quando habilitado) e processar localmente. Legendas: poucas fontes com legenda; não é parte central do pipeline atual. | Expiração de compartilhamentos e políticas da workspace; algumas gravações podem exigir login. | `transcreveai analyze "https://www.loom.com/share/..." --ai off --max-frames 20` | ✅ MVP |
| Google Drive (público) | Preferir link compartilhado público direto + `yt-dlp` para baixar para `source.mp4`. | Se bloqueado por redirecionamento: converter para link de download direto (formato `uc?export=download&id=...`) e validar novo URL; como fallback, baixar manualmente e processar local. Legendas: normalmente não disponíveis; transcript por áudio. | Links que parecem públicos mas exigem autenticação, anti-abuso e limitação de quota/download. | `transcreveai analyze "https://drive.google.com/file/d/.../view" --ai off --max-frames 20` | 🟡 MVP com ressalvas |
| Dropbox / direct file | `yt-dlp` para URL pública de arquivo (`?raw=1` ou `?dl=1`) quando aplicável. | Se `yt-dlp` não resolvesse o link, converter para URL de download cru e fazer ingestão via path local; manter versão local como fallback operacional. Legendas: normalmente não há; transcript por áudio. | URL caduca/expirada, links obsoletos de compartilhamento, limitação de banda. | `transcreveai analyze "https://www.dropbox.com/.../file.mp4?raw=1" --ai off --max-frames 20` | 🟡 MVP com ressalvas |
| Reddit | `yt-dlp` para post do subreddit com mídia hospedada no `v.redd.it`/`preview.redd.it`. | Se o extractor retornar erro de API/Player: extrair `https://...m3u8` da página e tratar como URL direta (ou baixar localmente, se possível). Legendas: quase inexistentes no Reddit; fallback por transcript de áudio. | Conteúdo removido, geoblocking, NSFW e links efêmeros; carregamento lento. | `transcreveai analyze "https://www.reddit.com/r/.../comments/.../" --ai off --max-frames 20` | 🟡 MVP com ressalvas |
| Twitch (clips/VOD) | `yt-dlp` para clip ou VOD público. | Se falha de token de sessão: reprocessar com cookie de navegador atualizado; para VOD protegido com atraso, esperar janela de processamento e retri. Legendas: depende da transmissão publicar captions; não garantido. | Clips/VOD expirados, regiões, restrição de acesso por horário/privacidade do stream. | `transcreveai analyze "https://www.twitch.tv/videos/..." --ai off --max-frames 20` | ✅ MVP |
| Arquivos locais | `fetch_media` já trata como caminho de arquivo e copia para `out/source.<ext>`. | Não há fallback remoto no modo local; se cópia falhar, validar path/permissões e reprocessar com URL equivalente quando disponível. Legendas: não aplicável; usar transcript por áudio. | Erro de path, codec não suportado, arquivo corrompido. | `transcreveai analyze ./video.mp4 --ai off --max-frames 20` | ✅ MVP |
| MP4/MOV/M3U8 (URL direta) | `yt-dlp` aceita a URL direta como fonte e aplica `format` + `merge_output_format=mp4`. | Se o downloader de URL direta quebrar, baixar arquivo pelo stream manualmente (e.g. `ffmpeg -i <url> -c copy`) e tratar como arquivo local. Legendas: para M3U8 dependem de `subtitles` embutidos; se ausentes, transcript por áudio substitui. | MIME/headers inconsistentes, conexões interrompidas, playlists HLS longas e fragmentadas. | `transcreveai analyze "https://.../video.mp4" --format best --ai off --max-frames 20` | ✅ MVP |

## Observação operacional

- A política atual de ingestão dá preferência a `yt-dlp` para qualquer URL.
- Para fontes onde o risco é alto, o procedimento recomendado é: tentar 1) URL pública direta 2) URL com cookies 3) download manual + análise local.
- `transcreveai` ainda não usa `--write-subs` no pipeline padrão; qualquer uso de caption precisa ser implementado como fallback operacional ou etapa de validação externa.

## Racional de risco por risco técnico

- **Maior risco**: Instagram/Reels, X/Twitter, LinkedIn, Reddit.
- **Risco médio**: TikTok, Google Drive, Dropbox, direct links em ambiente restrito.
- **Menor risco**: YouTube, Vimeo, Loom, Twitch, arquivos locais e URLs diretas bem formadas.
