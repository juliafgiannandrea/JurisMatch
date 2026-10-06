# JurisMatch

Busca semântica em petições iniciais de ADI/ADC do STF: dada uma consulta em linguagem natural,
devolve um ranking de petições com o trecho mais relevante e a página do PDF.

## Pipeline

| Etapa | O que faz | Onde |
|---|---|---|
| 1 | Download dos PDFs | `scrapping_processos_controle_concentrado/` |
| 2 | OCR + extração de texto | `extracao_texto_peticoes/` |
| 3 | Limpeza, chunking e metadados | `python -m jurismatch.pipeline_chunks` |
| 4 | Embeddings + índice (FAISS exato + BM25) | `python -m jurismatch.indexar` |
| 5 | Busca híbrida com ranking de petições | `python -m jurismatch.busca "consulta"` |

## Como rodar

```bash
source venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[dev]"

python -m jurismatch.pipeline_chunks      # gera dados/chunks.parquet e dados/relatorio_chunks.csv
python -m jurismatch.indexar              # gera dados/indice/ (demora na primeira vez: embeddings em CPU)
python -m jurismatch.busca "liberdade de imprensa e capital estrangeiro" --k 5
```

Opções da busca: `--modo hibrido|denso|lexical` e `--classe ADI|ADC`.

## Stack

- Chunks por seção e parágrafo, alvo de 350 tokens (teto 480), com cabeçalho `ADI 1234 | seção`.
- Embeddings: `intfloat/multilingual-e5-base` (prefixos `query: ` / `passage: `, vetores normalizados).
- Índice vetorial: FAISS `IndexFlatIP` (busca exata); metadados em Parquet.
- Lexical: BM25 (`bm25s`) com stopwords e stemmer do português.
- Ranking: MaxP por petição em cada sistema, fundidos por RRF (k = 60).

O estudo que justifica essas escolhas está em `docs/pesquisa/`. Parâmetros em `src/jurismatch/config.py`.

## Testes

```bash
pytest -q                                   # rápido, sem baixar modelo
JURISMATCH_TESTES_LENTOS=1 pytest -q        # inclui o teste com o modelo real
```

## Limitações conhecidas

- `ADI_4271`, `ADI_4376` e `ADI_4393` foram extraídas sem OCR (só o carimbo de assinatura); precisam
  ser reprocessadas na etapa 2. `dados/relatorio_chunks.csv` lista os arquivos nessa situação.
- Anexos digitalizados e notas de rodapé não são separados do corpo da petição.
- A detecção de seções é heurística (títulos numerados).
