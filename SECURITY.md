# Security

- `.env` deve ficar somente local e nunca entrar no Git.
- `outputs/` pode conter videos, audios, imagens e dados extraidos; por padrao tambem fica fora do Git.
- Chaves de API devem ser rotacionadas se forem coladas em chat, logs ou issues.
- Para deploy futuro, prefira secrets do provedor de infra em vez de arquivo `.env`.
