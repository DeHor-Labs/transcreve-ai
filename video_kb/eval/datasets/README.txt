Como adicionar casos ao dataset de eval
=======================================

Cada arquivo JSON segue o esquema:

{
  "version": "1",
  "description": "Descricao do dataset",
  "cases": [
    {
      "id": "identificador_unico_snake_case",
      "source": "URL publica ou path absoluto do video",
      "notes": "Descricao opcional do caso",
      "ground_truth_transcript": "Transcricao de referencia para calculo de WER (opcional)"
    }
  ]
}

Campos:
  id                        Obrigatorio. Unico, snake_case, sem espacos.
  source                    Obrigatorio. URL YouTube/Wikimedia ou path local.
  notes                     Opcional. Descricao humana do caso.
  ground_truth_transcript   Opcional. Se presente e nao-vazio, o eval calcula
                            Word Error Rate (WER) comparando com a transcricao
                            gerada. Se ausente ou vazio, WER fica null no relatorio.

Boas praticas para novos casos:
  - Use videos curtos (< 5 min) para manter o eval rapido.
  - Prefira videos de dominio publico ou com licenca livre.
  - Inclua pelo menos um caso com fala em portugues para testar pt-BR.
  - Inclua pelo menos um caso sem fala para testar OCR e visao.
  - Use IDs descritivos: "python_tutorial_30s", "news_clip_pt_2min".

Para rodar o eval com um dataset customizado:
  transcreveai eval --dataset video_kb/eval/datasets/meu_dataset.json --providers openai,local
