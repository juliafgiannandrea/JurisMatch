# JurisMatch — Etapa 3 (limpeza, chunking, metadados) e índice de busca: Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar os `.txt` já extraídos das petições iniciais de ADI/ADC em chunks limpos com metadados (`dados/chunks.parquet`) e em um índice de busca híbrida que devolve um ranking de petições com o melhor trecho e a página do PDF.

**Architecture:** Um pacote Python `jurismatch` com um módulo por responsabilidade: `paginas` (lê os marcadores de página) → `limpeza` (remove ruído e monta parágrafos) → `chunking` (empacota em chunks de ~350 tokens com cabeçalho de contexto) → `indexar` (embeddings + FAISS exato + BM25) → `busca` (MaxP por petição + fusão RRF). A linha *i* de `chunks.parquet` é o vetor *i* do FAISS e o documento *i* do BM25; esse alinhamento é a única "cola" entre os artefatos.

**Tech Stack:** Python ≥ 3.10, pandas + pyarrow (Parquet), sentence-transformers com `intfloat/multilingual-e5-base` em CPU, `faiss-cpu` (`IndexFlatIP`), `bm25s` + PyStemmer (português), pytest.

---

## Contexto para quem vai executar

### O que já existe no repositório

- `scrapping_processos_controle_concentrado/peticoes_processos_estruturantes/` — 102 PDFs (etapa 1) e `log_download.csv`.
- `extracao_texto_peticoes/texto_peticoes/` — 102 `.txt` (etapa 2) e `log_extracao.csv`. **Esta é a entrada deste plano.**
- `extracao_texto_peticoes/pontos_fortes_e_fracos.md` — revisão do script de extração.
- `venv/` — ambiente virtual já criado (ignorado pelo git).
- Os scripts das etapas 1 e 2 ainda **não** estão no repositório; a Julia vai adicioná-los nas pastas acima. Este plano não toca nelas.
- Só `.gitignore` e `README.md` estão versionados. Branch única, um commit.

### Formato dos `.txt`

- Nome: `{ADI|ADC}_{numero}_peticao_inicial.txt`. Quatro petições vêm em partes (`..._parte01.txt`, `..._parte02.txt`): ADI 2945, 3494, 4917 e 5624. São 102 arquivos e **97 petições**.
- Cada página começa com uma linha `[[pagina N | nativo]]`, `[[pagina N | ocr]]` ou `[[pagina N | vazia]]`. A numeração recomeça em 1 a cada parte.
- 4.536 páginas: 2.630 nativas, 1.902 de OCR (Tesseract), 4 vazias.
- Ruídos observados: número de página sozinho na linha; linhas quebradas no meio do parágrafo; em vários arquivos, uma linha em branco entre **todas** as linhas (espaçamento duplo); timbres de escritório repetidos em toda página; carimbos de assinatura digital; sumário com pontilhado; notas de rodapé misturadas ao corpo.

### Decisões de desenho (e por quê)

| Decisão | Escolha | Motivo |
|---|---|---|
| Unidade de corte | Seção numerada → parágrafo → sentença (só se o parágrafo estourar o teto) | Fronteiras naturais superam corte fixo em texto jurídico; chunking semântico não compensa o custo. |
| Tamanho | Alvo 350 tokens, teto 480, sem overlap | O e5 trunca em 512; overlap não mostrou ganho na literatura. Validar depois com um grid (200/350/500). |
| Contexto | Cabeçalho `ADI 5613 \| <seção>` prefixado ao texto embedado | Em corpus jurídico o erro típico é recuperar o trecho da petição errada; identificar o documento no chunk reduz isso. |
| Embedding | `intfloat/multilingual-e5-base` (MIT, 768 d, 512 tokens) | Roda em CPU; multilíngues modernos superam BERTs jurídicos em recuperação. Exige prefixos `query: ` / `passage: `. |
| Índice vetorial | FAISS `IndexFlatIP` + Parquet de metadados | Com ~8 mil vetores a busca exata leva milissegundos; é determinística e tem só duas dependências. Chroma (HNSW aproximado, métrica L2 por padrão, ~80 dependências) não traz vantagem nessa escala. |
| Lexical | `bm25s` com stopwords e stemmer do português | BM25 é competitivo em recuperação jurídica brasileira e acerta números de lei que o denso confunde. Nem FAISS nem Chroma fazem híbrido local. |
| Fusão | RRF (k = 60) sobre rankings de **petições** | Combina escalas incompatíveis sem ajuste de pesos. |
| Chunk → petição | MaxP (a petição vale o seu melhor chunk) | Imune ao tamanho do documento e já entrega o trecho a exibir. |

O estudo completo que sustenta essas escolhas está em `docs/pesquisa/2026-10-05-chunking-embeddings-banco-vetorial.md`.

### Achados no corpus que afetam a execução

1. **Três petições digitalizadas foram extraídas sem OCR.** Em `ADI_4271` (191 páginas), `ADI_4376` (56) e `ADI_4393` (16), todas as páginas estão marcadas como `nativo`, mas o único texto é o carimbo de assinatura digital do STF; o corpo da petição se perdeu. `ADI_4966` tem 1 página assim. É exatamente o risco "carimbos podem esconder páginas digitalizadas" descrito em `pontos_fortes_e_fracos.md`. **Corrigir isso é da etapa 2 e está fora deste plano**; o pipeline daqui apenas detecta e avisa (coluna `paginas_so_com_carimbo` do relatório). Até a correção, o corpus terá 95 petições com chunks, não 97.
2. **Anexos digitalizados** (leis, pareceres, procurações) vêm junto de algumas petições, sobretudo `ADI_3494` e `ADI_2945`, e geram centenas de chunks de OCR ruim. Não são removidos neste plano; o MaxP impede que dominem o ranking.
3. **Detecção de seção é heurística.** Só títulos numerados (`I. DOS FATOS`, `3. DO PEDIDO`, `II – Da legitimidade`) definem a seção. Em anexos de OCR ainda aparecem falsos títulos. Cerca de 16% dos chunks ficam sem seção.
4. **Notas de rodapé não são separadas do corpo.** Ficam no parágrafo ou viram parágrafos próprios. Limitação conhecida e aceita nesta versão.

### Fora do escopo (próximos planos)

- Conjunto de consultas rotuladas e avaliação (Recall@k, MRR, nDCG com `ranx`); grid de tamanhos de chunk e comparação de modelos de embedding.
- Resumo por petição, interface (Streamlit/Gradio) e reranker.
- Correção da extração/OCR da etapa 2.

### Sobre os comandos deste plano

| Tipo | Comandos | Efeito |
|---|---|---|
| Só leitura | `git status`, `pytest`, `python -m jurismatch.busca ...` | Não alteram nada (o `pytest` cria apenas `.pytest_cache/`, ignorado pelo git). |
| Modificam arquivos locais | `pip install ...` (dentro do `venv/`), `python -m jurismatch.pipeline_chunks`, `python -m jurismatch.indexar` | Instalam pacotes no `venv/` ou gravam em `dados/`. |
| Alteram o repositório **local** | `git add`, `git commit` | Criam commits locais. |
| Mexem no remoto / infraestrutura | **Nenhum** | Este plano não faz `git push` nem toca em infraestrutura. Não rode `git push` sem a Julia pedir. |

O download do modelo de embedding (~1,1 GB) acontece na primeira execução de `pipeline_chunks`/`indexar` e fica no cache do Hugging Face em `~/.cache/huggingface/`.

### O código deste plano já foi testado

Tudo, exceto `embeddings.py`, foi executado durante o planejamento: 44 testes passando e uma rodada de ponta a ponta nos 102 `.txt` reais com um embedder falso (7.904 chunks, índice construído em ~3 s, busca em ~10 ms). O modelo real não pôde ser baixado no ambiente de planejamento, então a contagem de tokens foi aproximada e **`embeddings.py` e os números finais de chunks são a parte não verificada**. Copie o código como está; se um teste falhar, investigue antes de alterar o teste.

---

## Estrutura de arquivos

```
JurisMatch/
├── pyproject.toml                      (novo) dependências e configuração do pytest
├── .gitignore                          (alterar) ignorar dados/ e o perfil do Chromium
├── README.md                           (alterar) como rodar
├── src/jurismatch/
│   ├── __init__.py
│   ├── config.py                       caminhos e parâmetros (único lugar)
│   ├── paginas.py                      nome do arquivo -> petição; texto -> páginas
│   ├── limpeza.py                      páginas -> linhas úteis -> blocos (título/parágrafo)
│   ├── chunking.py                     blocos -> chunks com metadados
│   ├── pipeline_chunks.py              CLI: .txt -> dados/chunks.parquet + relatório
│   ├── embeddings.py                   wrapper do modelo (prefixos, normalização)
│   ├── lexical.py                      BM25 em português
│   ├── indexar.py                      CLI: chunks.parquet -> dados/indice/
│   └── busca.py                        CLI e classe Buscador (MaxP + RRF)
├── tests/
│   ├── conftest.py                     embedder falso e chunks de exemplo
│   └── test_*.py                       um arquivo de teste por módulo
└── dados/                              (gerado, não versionado)
    ├── chunks.parquet
    ├── relatorio_chunks.csv
    └── indice/  (faiss.index, embeddings.npy, chunks.parquet, bm25/, manifesto.json)
```

Esquema de `chunks.parquet` (uma linha por chunk):

| Coluna | Tipo | Conteúdo |
|---|---|---|
| `chunk_id` | str | `ADI_5613_0007` (sequencial dentro da petição, atravessa as partes) |
| `doc_id` | str | `ADI_5613` |
| `classe`, `numero` | str, int | `ADI`, `5613` |
| `arquivo_pdf` | str | PDF (da parte) onde o chunk está |
| `pagina_inicio`, `pagina_fim` | int | páginas do PDF `arquivo_pdf` |
| `metodo_extracao` | str | `nativo`, `ocr` ou `misto` |
| `secao` | str | título da seção vigente (pode ser vazio) |
| `n_tokens` | int | tokens de `texto_embedding` no tokenizer do modelo |
| `texto` | str | texto limpo, para exibir |
| `texto_embedding` | str | cabeçalho de contexto + texto, para embedar |
| `hash` | str | SHA-1 de `texto_embedding` (chave do cache de embeddings) |
| `versao_pipeline` | str | `config.VERSAO_PIPELINE` |

---

### Task 1: Estrutura do projeto

**Files:**
- Create: `pyproject.toml`
- Create: `src/jurismatch/__init__.py`
- Create: `src/jurismatch/config.py`
- Modify: `.gitignore` (acrescentar ao final)

- [ ] **Step 1: Criar `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "jurismatch"
version = "0.1.0"
description = "Busca semântica em petições iniciais de ADI/ADC do STF"
requires-python = ">=3.10"
dependencies = [
    "numpy>=1.26",
    "pandas>=2.2",
    "pyarrow>=15",
    "faiss-cpu>=1.8",
    "bm25s>=0.2",
    "PyStemmer>=2.2",
    "sentence-transformers>=3.0",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: Criar `src/jurismatch/__init__.py`**

```python
"""JurisMatch: busca semântica em petições iniciais de ADI/ADC do STF."""
```

- [ ] **Step 3: Criar `src/jurismatch/config.py`**

```python
"""Caminhos e parâmetros do projeto. Único lugar onde eles são definidos."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

# Entradas (produzidas pelas etapas 1 e 2)
DIR_TXT = RAIZ / "extracao_texto_peticoes" / "texto_peticoes"
DIR_PDF = RAIZ / "scrapping_processos_controle_concentrado" / "peticoes_processos_estruturantes"

# Saídas da etapa 3 (não versionadas no git)
DIR_DADOS = RAIZ / "dados"
ARQ_CHUNKS = DIR_DADOS / "chunks.parquet"
DIR_INDICE = DIR_DADOS / "indice"

# Embeddings: multilingual-e5 exige os prefixos abaixo (ver card do modelo)
MODELO_EMBEDDING = "intfloat/multilingual-e5-base"
PREFIXO_CONSULTA = "query: "
PREFIXO_PASSAGEM = "passage: "

# Chunking: alvo de tokens por chunk e teto rígido (o modelo trunca em 512)
ALVO_TOKENS = 350
TETO_TOKENS = 480

# Fusão híbrida (Reciprocal Rank Fusion)
RRF_K = 60

# Mude este valor sempre que a limpeza ou o chunking mudarem de comportamento
VERSAO_PIPELINE = "1"
```

- [ ] **Step 4: Acrescentar ao final de `.gitignore`**

```gitignore

# JurisMatch
dados/
scrapping_processos_controle_concentrado/.perfil_chromium_stf/
```

O perfil do Chromium usado no scraping contém cookies e histórico de navegação; não deve ir para o git. Os PDFs (172 MB) e os `.txt` continuam fora deste plano: não os adicione ao git aqui.

- [ ] **Step 5: Instalar as dependências no `venv/` existente**

```bash
source venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[dev]"
```

O primeiro `pip install` traz o PyTorch só para CPU (evita baixar ~2 GB de bibliotecas CUDA). Ambos modificam apenas o `venv/`.

Expected: termina com `Successfully installed ... jurismatch-0.1.0 ...`.

- [ ] **Step 6: Verificar a instalação**

Run: `python -c "import jurismatch.config as c, faiss, bm25s, Stemmer, sentence_transformers; print(c.DIR_TXT.exists(), faiss.__version__)"`

Expected: `True` seguido da versão do FAISS (1.8 ou superior). Se imprimir `False`, o caminho `DIR_TXT` em `config.py` não corresponde à pasta dos `.txt`: pare e avise.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore src/jurismatch/__init__.py src/jurismatch/config.py
git commit -m "chore: estrutura do pacote jurismatch e dependências"
```

---

### Task 2: Leitura das páginas e identificação da petição

**Files:**
- Create: `src/jurismatch/paginas.py`
- Test: `tests/test_paginas.py`

- [ ] **Step 1: Escrever os testes em `tests/test_paginas.py`**

```python
from pathlib import Path

import pytest

from jurismatch.paginas import agrupar_por_peticao, identificar_arquivo, ler_paginas

TEXTO = (
    "[[pagina 1 | nativo]]\n\nPrimeira página.\n\n1\n\n"
    "[[pagina 2 | ocr]]\n\nSegunda página.\n\n"
    "[[pagina 3 | vazia]]\n"
)


def test_ler_paginas_separa_por_marcador():
    paginas = ler_paginas(TEXTO)
    assert [(p.numero, p.metodo) for p in paginas] == [(1, "nativo"), (2, "ocr"), (3, "vazia")]
    assert "Primeira página." in paginas[0].texto
    assert "[[pagina" not in paginas[0].texto
    assert paginas[2].texto == ""


def test_identificar_arquivo_simples():
    a = identificar_arquivo(Path("ADC_100_peticao_inicial.txt"))
    assert (a.classe, a.numero, a.parte, a.doc_id) == ("ADC", 100, 1, "ADC_100")
    assert a.arquivo_pdf == "ADC_100_peticao_inicial.pdf"


def test_identificar_arquivo_com_parte():
    a = identificar_arquivo(Path("ADI_3494_peticao_inicial_parte03.txt"))
    assert (a.doc_id, a.parte) == ("ADI_3494", 3)
    assert a.arquivo_pdf == "ADI_3494_peticao_inicial_parte03.pdf"


def test_identificar_arquivo_fora_do_padrao():
    with pytest.raises(ValueError):
        identificar_arquivo(Path("log_extracao.txt"))


def test_agrupar_por_peticao_junta_partes(tmp_path):
    for nome in [
        "ADI_2945_peticao_inicial_parte02.txt",
        "ADI_2945_peticao_inicial_parte01.txt",
        "ADC_27_peticao_inicial.txt",
    ]:
        (tmp_path / nome).write_text("[[pagina 1 | nativo]]\n\nx\n", encoding="utf-8")
    (tmp_path / "log_extracao.csv").write_text("a;b\n", encoding="utf-8")
    grupos = agrupar_por_peticao(tmp_path)
    assert sorted(grupos) == ["ADC_27", "ADI_2945"]
    assert [a.parte for a in grupos["ADI_2945"]] == [1, 2]
```

- [ ] **Step 2: Rodar e confirmar que falham**

Run: `pytest tests/test_paginas.py -q`

Expected: erro de coleta com `ModuleNotFoundError: No module named 'jurismatch.paginas'`.

- [ ] **Step 3: Implementar `src/jurismatch/paginas.py`**

```python
"""Leitura dos .txt da etapa 2: identifica a petição e separa o texto por página."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

RE_MARCADOR = re.compile(r"^\[\[pagina (\d+) \| ([a-z_]+)\]\][ \t]*$", re.MULTILINE)
RE_NOME = re.compile(r"^(ADI|ADC)_(\d+)_peticao_inicial(?:_parte(\d+))?\.txt$")


@dataclass(frozen=True)
class Pagina:
    numero: int
    metodo: str  # "nativo", "ocr" ou "vazia"
    texto: str


@dataclass(frozen=True)
class ArquivoPeticao:
    caminho: Path
    classe: str  # "ADI" ou "ADC"
    numero: int
    parte: int  # 1 quando a petição não foi dividida em partes

    @property
    def doc_id(self) -> str:
        return f"{self.classe}_{self.numero}"

    @property
    def arquivo_pdf(self) -> str:
        return self.caminho.with_suffix(".pdf").name


def identificar_arquivo(caminho: Path) -> ArquivoPeticao:
    m = RE_NOME.match(caminho.name)
    if m is None:
        raise ValueError(f"Nome de arquivo fora do padrão: {caminho.name}")
    return ArquivoPeticao(
        caminho=caminho,
        classe=m.group(1),
        numero=int(m.group(2)),
        parte=int(m.group(3) or 1),
    )


def ler_paginas(texto: str) -> list[Pagina]:
    """Divide o texto nos marcadores [[pagina N | metodo]]."""
    marcadores = list(RE_MARCADOR.finditer(texto))
    paginas = []
    for i, m in enumerate(marcadores):
        fim = marcadores[i + 1].start() if i + 1 < len(marcadores) else len(texto)
        paginas.append(
            Pagina(numero=int(m.group(1)), metodo=m.group(2), texto=texto[m.end():fim].strip("\n"))
        )
    return paginas


def agrupar_por_peticao(dir_txt: Path) -> dict[str, list[ArquivoPeticao]]:
    """Mapa doc_id -> arquivos da petição, em ordem de parte."""
    grupos: dict[str, list[ArquivoPeticao]] = {}
    for caminho in sorted(dir_txt.glob("*.txt")):
        arquivo = identificar_arquivo(caminho)
        grupos.setdefault(arquivo.doc_id, []).append(arquivo)
    for arquivos in grupos.values():
        arquivos.sort(key=lambda a: a.parte)
    return grupos
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `pytest tests/test_paginas.py -q`

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/jurismatch/paginas.py tests/test_paginas.py
git commit -m "feat: leitura de páginas e identificação da petição"
```

---

### Task 3: Limpeza — normalização, ruído, cabeçalhos repetidos e sumário

**Files:**
- Create: `src/jurismatch/limpeza.py`
- Test: `tests/test_limpeza.py`

- [ ] **Step 1: Escrever os testes em `tests/test_limpeza.py`**

```python
from jurismatch.limpeza import Linha, eh_ruido, limpar_paginas, linhas_repetidas, normalizar
from jurismatch.paginas import Pagina


def L(texto, pagina=1, metodo="nativo"):
    return Linha(texto, pagina, metodo)


def test_normalizar_troca_nbsp_ligadura_e_espacos():
    assert normalizar("  art. 5º   da\tCons­tituição eﬁcaz ") == "art. 5º da Constituição eficaz"


def test_normalizar_preserva_acentos_compostos():
    assert normalizar("ação") == "ação"


def test_eh_ruido():
    assert eh_ruido("12")
    assert eh_ruido("Página 3 de 20")
    assert eh_ruido("Signature Not Verified")
    assert eh_ruido("Assinado por FULANO DE TAL:123 em 19/03/2010 12:49:37")
    assert eh_ruido("_______________________________")
    assert eh_ruido("(...)")
    assert not eh_ruido("9868/99, propor")
    assert not eh_ruido("AÇÃO DIRETA DE INCONSTITUCIONALIDADE")


def test_linhas_repetidas_detecta_cabecalho_com_numero_variavel():
    corpo = ["alfa", "beta", "gama", "delta", "épsilon", "zeta"]
    paginas = [["Escritório X Advogados", f"texto sobre {c}", f"Rua Y, 10 - fl. {i}"] for i, c in enumerate(corpo)]
    assert linhas_repetidas(paginas) == {"escritório x advogados", "rua y, # - fl. #"}


def test_linhas_repetidas_ignora_documento_curto():
    assert linhas_repetidas([["Cabeçalho"], ["Cabeçalho"], ["Cabeçalho"]]) == set()


def test_limpar_paginas_remove_sumario_ruido_e_cabecalho():
    temas = ["alfa", "beta", "gama", "delta", "épsilon"]
    paginas = [
        Pagina(n, "nativo", f"Timbre do Escritório\n\nParágrafo sobre {tema}.\n\n{n}")
        for n, tema in enumerate(temas, start=1)
    ]
    paginas.insert(
        1,
        Pagina(99, "nativo", "SUMÁRIO\nI. FATOS ........ 3\nII. DIREITO ........ 5\nIII. PEDIDO ........ 9"),
    )
    paginas.append(Pagina(7, "vazia", ""))
    textos = [l.texto for l in limpar_paginas(paginas) if l.texto]
    assert textos == [f"Parágrafo sobre {tema}." for tema in temas]
```

- [ ] **Step 2: Rodar e confirmar que falham**

Run: `pytest tests/test_limpeza.py -q`

Expected: erro de coleta com `ModuleNotFoundError: No module named 'jurismatch.limpeza'`.

- [ ] **Step 3: Implementar a primeira metade de `src/jurismatch/limpeza.py`**

As constantes de título e de parágrafo (`_NUM`, `RE_TITULO_*`, `RE_INICIO_PARAGRAFO`, `PRONOMES_ENCLITICOS`) e a classe `Bloco` só serão usadas na Task 4, mas já ficam declaradas aqui.

```python
"""Limpeza conservadora do texto extraído e montagem de parágrafos.

Entrada: páginas de um arquivo (jurismatch.paginas.Pagina).
Saída: blocos (título ou parágrafo), cada um sabendo de que páginas veio.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from jurismatch.paginas import Pagina

MAIUSCULAS = "A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ"

_TROCAS = {
    " ": " ",  # espaço não separável
    "­": "",  # hífen condicional
    "​": "",  # espaço de largura zero
    "﻿": "",  # BOM
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
}
_TABELA_TROCAS = str.maketrans(_TROCAS)

# Linhas que nunca fazem parte do argumento da petição
RE_RUIDO = [
    re.compile(r"^\d{1,4}$"),  # número de página solto
    re.compile(r"^(p[áa]gina|p[áa]g\.?|p\.|fls?\.?)\s*\d+(\s*(de|/)\s*\d+)?$", re.IGNORECASE),
    re.compile(r"^signature not verified$", re.IGNORECASE),
    re.compile(r"^assinado por .+ em \d{2}/\d{2}/\d{4}", re.IGNORECASE),
    re.compile(r"^documento assinado digitalmente", re.IGNORECASE),
    re.compile(r"documento pode ser acessado no endere[çc]o eletr[ôo]nico", re.IGNORECASE),
    re.compile(r"autenticacao/autenticarDocumento", re.IGNORECASE),
    re.compile(r"validacaodocumento", re.IGNORECASE),
]

RE_PONTILHADO_SUMARIO = re.compile(r"\.{5,}\s*\d+\s*$")
# Título numerado: "I. DOS FATOS", "II – Da legitimidade", "3. DO PEDIDO", "II.2 ADVOCACIA"
_NUM = r"(?:X{0,3}(?:IX|IV|V?I{1,3}|V|X)|[1-9]\d?)"  # I a XXXIX, ou 1 a 99
RE_TITULO_COM_SEPARADOR = re.compile(
    rf"^(?P<num>{_NUM})(?:\.\d{{1,2}}){{0,3}}\s*[.\-–—)](?P<esp>\s*)(?P<resto>[^\W\d_].*)$"
)
RE_TITULO_COM_SUBNUMERO = re.compile(rf"^{_NUM}(?:\.\d{{1,2}}){{1,3}}\s+(?P<resto>[^\W\d_].*)$")
RE_INICIO_PARAGRAFO = re.compile(r"^(\d{1,3}[.)]|[a-z]\))\s+\S")
PRONOMES_ENCLITICOS = {
    "se", "me", "te", "lhe", "lhes", "nos", "vos",
    "o", "a", "os", "as", "lo", "la", "los", "las", "no", "na", "nos", "nas",
}


@dataclass(frozen=True)
class Linha:
    texto: str  # "" representa linha em branco
    pagina: int
    metodo: str


@dataclass(frozen=True)
class Bloco:
    texto: str
    tipo: str  # "titulo" ou "paragrafo"
    pagina_inicio: int
    pagina_fim: int
    metodos: frozenset[str]


def normalizar(texto: str) -> str:
    """Normaliza Unicode e espaços de uma linha, sem mexer em acentos ou caixa."""
    texto = unicodedata.normalize("NFC", texto).translate(_TABELA_TROCAS)
    return re.sub(r"[ \t]+", " ", texto).strip()


def eh_ruido(linha: str) -> bool:
    """Número de página, carimbo de assinatura ou linha sem conteúdo alfanumérico."""
    if any(r.search(linha) for r in RE_RUIDO):
        return True
    sem_espaco = linha.replace(" ", "")
    if len(sem_espaco) >= 5:
        alfanum = sum(c.isalnum() for c in sem_espaco)
        if alfanum / len(sem_espaco) < 0.5:
            return True
    return False


def _chave(linha: str) -> str:
    return re.sub(r"\d+", "#", linha.lower())


def linhas_repetidas(paginas_normalizadas: list[list[str]]) -> set[str]:
    """Chaves de linhas que aparecem em pelo menos metade das páginas (cabeçalho/rodapé)."""
    com_texto = [p for p in paginas_normalizadas if any(p)]
    if len(com_texto) < 4:
        return set()
    contagem: Counter[str] = Counter()
    for linhas in com_texto:
        contagem.update({_chave(l) for l in linhas if len(l) >= 4})
    minimo = max(3, len(com_texto) / 2)
    return {chave for chave, n in contagem.items() if n >= minimo}


def eh_pagina_de_sumario(linhas: list[str]) -> bool:
    return sum(bool(RE_PONTILHADO_SUMARIO.search(l)) for l in linhas) >= 3


def limpar_paginas(paginas: list[Pagina]) -> list[Linha]:
    """Devolve as linhas úteis do arquivo, em ordem, com página e método de origem."""
    normalizadas = [[normalizar(l) for l in p.texto.split("\n")] for p in paginas]
    repetidas = linhas_repetidas(normalizadas)
    saida: list[Linha] = []
    for pagina, linhas in zip(paginas, normalizadas):
        if pagina.metodo == "vazia" or eh_pagina_de_sumario(linhas):
            continue
        for texto in linhas:
            if texto == "":
                saida.append(Linha("", pagina.numero, pagina.metodo))
            elif _chave(texto) in repetidas or eh_ruido(texto):
                continue
            else:
                saida.append(Linha(texto, pagina.numero, pagina.metodo))
        saida.append(Linha("", pagina.numero, pagina.metodo))
    return saida
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `pytest tests/test_limpeza.py -q`

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/jurismatch/limpeza.py tests/test_limpeza.py
git commit -m "feat: limpeza de linhas (unicode, ruído, cabeçalhos repetidos, sumário)"
```

---

### Task 4: Limpeza — títulos e montagem de parágrafos

**Files:**
- Modify: `src/jurismatch/limpeza.py` (acrescentar ao final)
- Modify: `tests/test_limpeza.py`

- [ ] **Step 1: Substituir o bloco de imports de `tests/test_limpeza.py`**

Troque as duas linhas de import do topo do arquivo por:

```python
from jurismatch.limpeza import (
    Linha,
    eh_destaque,
    eh_ruido,
    eh_titulo,
    limpar_paginas,
    linhas_repetidas,
    montar_blocos,
    normalizar,
)
from jurismatch.paginas import Pagina
```

- [ ] **Step 2: Acrescentar os testes ao final de `tests/test_limpeza.py`**

```python
def test_eh_titulo():
    assert eh_titulo("I. NECESSÁRIA DISTRIBUIÇÃO POR PREVENÇÃO", True)
    assert eh_titulo("I- DA DISTRIBUIÇÃO POR DEPENDÊNCIA ÀS ADIs 7.827 e 7.839", False)
    assert eh_titulo("I –O OBJETO DESTA AÇÃO DIRETA DE INCONSTITUCIONALIDADE", True)
    assert eh_titulo("II – Da legitimidade ativa", True)
    assert eh_titulo("3. DO PEDIDO CAUTELAR", True)
    assert eh_titulo("II.2 ADVOCACIA PRIVADA E PÚBLICA", True)
    assert not eh_titulo("AÇÃO DIRETA DE INCONSTITUCIONALIDADE", True)  # sem numeração: é destaque
    assert not eh_titulo("INCONSTITUCIONALIDADE DA LEI IMPUGNADA", True)
    assert not eh_titulo("V.Exa., muito respeitosamente, ajuizar a presente", True)
    assert not eh_titulo("I, “a” e no art. 103, inciso IX, da Constituição Federal,", True)
    assert not eh_titulo("L. A. MACHADO, PROFESSOR TITULAR DA FACULDADE DE DIREITO", True)
    assert not eh_titulo("94-27-95 1:15: 16 RECIBIDO DE:~553412951 P.04", True)
    assert not eh_titulo("9.504/97. PROIBIÇÃO IMPOSTA AOS CANDIDATOS", True)
    assert not eh_titulo("5. Ademais, os adeptos desse entendimento afirmam haver", True)
    assert not eh_titulo(
        "II - Quando a produção ocorrer na plataforma continental, no mar territorial ou na", True
    )


def test_eh_destaque():
    assert eh_destaque("AÇÃO DIRETA DE INCONSTITUCIONALIDADE")
    assert not eh_destaque("em face do art. 1º da Lei 8540/92")


def test_montar_blocos_destaque_vira_paragrafo_proprio():
    linhas = [
        L("EXCELENTÍSSIMO SENHOR MINISTRO PRESIDENTE DO"),
        L("SUPREMO TRIBUNAL FEDERAL"),
        L(""),
        L("A ASSOCIAÇÃO X vem propor a presente"),
        L(""),
        L("AÇÃO DIRETA DE INCONSTITUCIONALIDADE"),
        L(""),
        L("em face da Lei Y."),
    ]
    blocos = montar_blocos(linhas)
    assert [(b.tipo, b.texto) for b in blocos] == [
        ("paragrafo", "EXCELENTÍSSIMO SENHOR MINISTRO PRESIDENTE DO SUPREMO TRIBUNAL FEDERAL"),
        ("paragrafo", "A ASSOCIAÇÃO X vem propor a presente AÇÃO DIRETA DE INCONSTITUCIONALIDADE em face da Lei Y."),
    ]


def test_montar_blocos_rejunta_linhas_com_espacamento_duplo():
    linhas = [
        L("ABRAFRIGO, pessoa jurídica de direito privado, com"),
        L(""),
        L("sede em Curitiba, CEP 80.540-"),
        L(""),
        L("290, vem propor a presente ação."),
        L(""),
        L("Outro parágrafo começa aqui."),
    ]
    blocos = montar_blocos(linhas)
    assert [b.texto for b in blocos] == [
        "ABRAFRIGO, pessoa jurídica de direito privado, com sede em Curitiba, CEP 80.540-290, "
        "vem propor a presente ação.",
        "Outro parágrafo começa aqui.",
    ]


def test_montar_blocos_hifenizacao():
    blocos = montar_blocos([L("norma incons-"), L("titucional que declara-"), L("se nula.")])
    assert blocos[0].texto == "norma inconstitucional que declara-se nula."


def test_montar_blocos_paragrafo_atravessa_pagina():
    linhas = [
        L("5. O parágrafo começa na página dois e", 2, "nativo"),
        L("", 2, "nativo"),
        L("termina na página três.", 3, "ocr"),
        L("6. Novo parágrafo numerado.", 3, "ocr"),
    ]
    blocos = montar_blocos(linhas)
    assert len(blocos) == 2
    assert (blocos[0].pagina_inicio, blocos[0].pagina_fim) == (2, 3)
    assert blocos[0].metodos == frozenset({"nativo", "ocr"})
    assert blocos[1].texto == "6. Novo parágrafo numerado."


def test_montar_blocos_titulo_em_duas_linhas():
    linhas = [
        L("Fim do parágrafo anterior."),
        L(""),
        L("II. REQUISITOS FORMAIS: OBJETO DESTA ADC E"),
        L("PERTINÊNCIA TEMÁTICA"),
        L(""),
        L("Texto da seção."),
    ]
    blocos = montar_blocos(linhas)
    assert [(b.tipo, b.texto) for b in blocos] == [
        ("paragrafo", "Fim do parágrafo anterior."),
        ("titulo", "II. REQUISITOS FORMAIS: OBJETO DESTA ADC E PERTINÊNCIA TEMÁTICA"),
        ("paragrafo", "Texto da seção."),
    ]


def test_montar_blocos_inciso_de_lei_nao_vira_titulo():
    linhas = [
        L("Art. 3º Compete ao Conselho:"),
        L("I - Convocar reunião extraordinária"),
        L("II - Aprovar o regimento interno."),
    ]
    assert all(b.tipo == "paragrafo" for b in montar_blocos(linhas))
```

- [ ] **Step 3: Rodar e confirmar que falham**

Run: `pytest tests/test_limpeza.py -q`

Expected: erro de coleta com `ImportError: cannot import name 'eh_destaque' from 'jurismatch.limpeza'`.

- [ ] **Step 4: Acrescentar ao final de `src/jurismatch/limpeza.py`**

Como a montagem funciona: uma linha continua o parágrafo aberto, a menos que (a) comece com numeração de parágrafo ou alínea (`5. `, `a) `), ou (b) venha depois de linha em branco **e** o parágrafo aberto já termine em pontuação final **e** a linha não comece em minúscula. A regra (b) é o que permite rejuntar arquivos com espaçamento duplo, em que há linha em branco entre todas as linhas.

```python
def _proporcao_maiusculas(texto: str) -> float:
    letras = [c for c in texto if c.isalpha()]
    if len(letras) < 4:
        return 0.0
    return sum(c.isupper() for c in letras) / len(letras)


def termina_frase(texto: str) -> bool:
    return texto.rstrip("\"'”’»)]").endswith((".", "!", "?", ":", ";"))


def eh_titulo(linha: str, anterior_terminou: bool) -> bool:
    """Título de seção: numeração (romana ou arábica) seguida de texto em maiúsculas,
    ou numeral romano + travessão + título curto em caixa mista."""
    if len(linha) > 160 or linha.endswith((",", ";")):
        return False
    m = RE_TITULO_COM_SEPARADOR.match(linha)
    if m is None:
        m = RE_TITULO_COM_SUBNUMERO.match(linha)
        return bool(m) and _proporcao_maiusculas(m.group("resto")) >= 0.8
    if _proporcao_maiusculas(m.group("resto")) >= 0.8:
        return True
    return (
        anterior_terminou
        and m.group("num")[0] in "IVXL"
        and bool(m.group("esp"))
        and m.group("resto")[0].isupper()
        and len(linha) <= 80
        and len(linha.split()) <= 10
        and "," not in linha
        and not linha.endswith((".", ":"))
    )


def eh_destaque(linha: str) -> bool:
    """Linha curta toda em maiúsculas (endereçamento, nome da ação, timbre)."""
    return len(linha) <= 160 and len(linha.split()) <= 20 and _proporcao_maiusculas(linha) >= 0.9


def _juntar(anterior: str, proxima: str) -> str:
    """Rejunta duas linhas do mesmo parágrafo, desfazendo hifenização de fim de linha."""
    if anterior.endswith("-") and len(anterior) > 1 and anterior[-2].isalnum():
        primeira = re.match(r"\w+", proxima)
        palavra = primeira.group(0).lower() if primeira else ""
        if proxima[0].isdigit() or palavra in PRONOMES_ENCLITICOS:
            return anterior + proxima  # "80.540-" + "290", "declara-" + "se"
        if proxima[0].islower():
            return anterior[:-1] + proxima  # "constitu-" + "cional"
    return anterior + " " + proxima


def montar_blocos(linhas: list[Linha]) -> list[Bloco]:
    """Agrupa linhas em parágrafos e títulos, preservando o intervalo de páginas."""
    blocos: list[Bloco] = []
    texto = ""
    pag_ini = pag_fim = 0
    metodos: set[str] = set()
    houve_branco = True
    em_destaque = False  # o parágrafo aberto é um bloco de linhas em maiúsculas
    titulo_aberto = False  # a linha anterior foi um título (pode continuar na próxima)

    def fechar():
        nonlocal texto, metodos
        if texto:
            blocos.append(Bloco(texto, "paragrafo", pag_ini, pag_fim, frozenset(metodos)))
        texto, metodos = "", set()

    for linha in linhas:
        if linha.texto == "":
            houve_branco = True
            titulo_aberto = False
            continue
        t = linha.texto
        anterior_terminou = texto == "" or em_destaque or termina_frase(texto)
        destaque = eh_destaque(t)

        # Título em caixa mista só é aceito depois de ponto final (incisos de lei vêm depois de
        # ":" ou ";") e em página nativa (em OCR, anexos digitalizados geram falsos títulos).
        apos_ponto = texto == "" or em_destaque or texto.rstrip("\"'”’»)]").endswith((".", "!", "?"))
        if eh_titulo(t, apos_ponto and linha.metodo == "nativo"):
            fechar()
            blocos.append(Bloco(t, "titulo", linha.pagina, linha.pagina, frozenset({linha.metodo})))
            titulo_aberto, em_destaque, houve_branco = True, False, False
            continue
        if titulo_aberto and destaque and len(blocos[-1].texto) < 300:
            ant = blocos.pop()  # título quebrado em duas linhas
            blocos.append(
                Bloco(f"{ant.texto} {t}", "titulo", ant.pagina_inicio, linha.pagina, ant.metodos | {linha.metodo})
            )
            houve_branco = False
            continue
        titulo_aberto = False

        if destaque and anterior_terminou:
            novo = not em_destaque
            em_destaque = True
        elif em_destaque:
            novo, em_destaque = True, False
        else:
            novo = (
                texto == ""
                or bool(RE_INICIO_PARAGRAFO.match(t))
                or (houve_branco and termina_frase(texto) and not t[0].islower())
            )
        if novo:
            fechar()
            texto, pag_ini = t, linha.pagina
        else:
            texto = _juntar(texto, t)
        pag_fim = linha.pagina
        metodos.add(linha.metodo)
        houve_branco = False
    fechar()
    return blocos
```

- [ ] **Step 5: Rodar e confirmar que passam**

Run: `pytest tests/test_limpeza.py -q`

Expected: `14 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/jurismatch/limpeza.py tests/test_limpeza.py
git commit -m "feat: detecção de títulos e montagem de parágrafos com páginas"
```

---

### Task 5: Chunking com metadados

**Files:**
- Create: `src/jurismatch/chunking.py`
- Test: `tests/test_chunking.py`

- [ ] **Step 1: Escrever os testes em `tests/test_chunking.py`**

Os testes usam contagem de palavras como contador de tokens (`contar`), com alvo 20 e teto 40, para ficarem legíveis.

```python
from jurismatch.chunking import cabecalho, dividir_em_sentencas, gerar_chunks
from jurismatch.limpeza import Bloco


def contar(texto):
    return len(texto.split())


def P(texto, pag_ini=1, pag_fim=None, metodo="nativo"):
    return Bloco(texto, "paragrafo", pag_ini, pag_fim or pag_ini, frozenset({metodo}))


def T(texto, pag=1):
    return Bloco(texto, "titulo", pag, pag, frozenset({"nativo"}))


def chunks_de(blocos, **kw):
    params = dict(doc_id="ADI_1", classe="ADI", numero=1, arquivo_pdf="ADI_1_peticao_inicial.pdf",
                  contar_tokens=contar, alvo=20, teto=40)
    params.update(kw)
    return gerar_chunks(blocos, **params)[0]


def test_dividir_em_sentencas_respeita_abreviacoes():
    texto = "Conforme o art. 5º da CF, cabe a ação. Ver fls. 10 dos autos. O Min. Relator decidiu."
    assert dividir_em_sentencas(texto) == [
        "Conforme o art. 5º da CF, cabe a ação.",
        "Ver fls. 10 dos autos.",
        "O Min. Relator decidiu.",
    ]


def test_cabecalho():
    assert cabecalho("ADI", 5613, "I – O OBJETO") == "ADI 5613 | I – O OBJETO"
    assert cabecalho("ADC", 27, "") == "ADC 27"


def test_agrupa_paragrafos_ate_o_alvo():
    blocos = [P("um dois três quatro cinco seis sete oito."), P("nove dez onze doze treze catorze quinze."),
              P("alfa beta gama delta épsilon zeta eta teta iota capa.")]
    chunks = chunks_de(blocos)
    assert [c["texto"] for c in chunks] == [
        "um dois três quatro cinco seis sete oito.\n\nnove dez onze doze treze catorze quinze.",
        "alfa beta gama delta épsilon zeta eta teta iota capa.",
    ]
    assert [c["chunk_id"] for c in chunks] == ["ADI_1_0000", "ADI_1_0001"]


def test_titulo_abre_chunk_e_define_secao():
    blocos = [P("Introdução curta da petição aqui."), T("I. DOS FATOS"), P("Os fatos são estes."),
              T("II. DO DIREITO"), P("O direito é este.")]
    chunks = chunks_de(blocos)
    assert [c["secao"] for c in chunks] == ["", "I. DOS FATOS", "II. DO DIREITO"]
    assert chunks[1]["texto"] == "I. DOS FATOS\n\nOs fatos são estes."
    assert chunks[1]["texto_embedding"] == "ADI 1 | I. DOS FATOS\nI. DOS FATOS\n\nOs fatos são estes."


def test_titulos_consecutivos_ficam_no_mesmo_chunk():
    chunks = chunks_de([T("I. DO MÉRITO"), T("I.1 DOS FATOS"), P("Os fatos são estes aqui.")])
    assert len(chunks) == 1
    assert chunks[0]["secao"] == "I.1 DOS FATOS"


def test_paragrafo_gigante_e_quebrado_respeitando_o_teto():
    sentencas = [" ".join(f"p{i}_{j}" for j in range(9)) + "." for i in range(12)]
    chunks = chunks_de([P(" ".join(sentencas), 3, 5)])
    assert len(chunks) > 1
    assert all(c["n_tokens"] <= 40 for c in chunks)
    assert " ".join(c["texto"] for c in chunks) == " ".join(sentencas)
    assert all((c["pagina_inicio"], c["pagina_fim"]) == (3, 5) for c in chunks)


def test_paginas_e_metodo_misto():
    chunks = chunks_de([P("um dois três quatro cinco.", 2, 2, "nativo"), P("seis sete oito nove dez.", 2, 3, "ocr")])
    assert len(chunks) == 1
    c = chunks[0]
    assert (c["pagina_inicio"], c["pagina_fim"], c["metodo_extracao"]) == (2, 3, "misto")


def test_continua_numeracao_e_secao_entre_partes():
    chunks, secao = gerar_chunks(
        [P("Continuação do argumento na parte dois.")],
        doc_id="ADI_1", classe="ADI", numero=1, arquivo_pdf="ADI_1_peticao_inicial_parte02.pdf",
        contar_tokens=contar, indice_inicial=7, secao_inicial="III. DO MÉRITO",
    )
    assert chunks[0]["chunk_id"] == "ADI_1_0007"
    assert chunks[0]["secao"] == "III. DO MÉRITO"
    assert secao == "III. DO MÉRITO"


def test_descarta_resto_sem_conteudo():
    assert chunks_de([P("1 2 3 - 4")]) == []


def test_muitos_titulos_seguidos_nao_estouram_o_teto():
    titulos = [T(f"{i}. ITEM EM MAIÚSCULAS DE UM ÍNDICE DIGITALIZADO") for i in range(30)]
    chunks = chunks_de(titulos)
    assert len(chunks) > 1
    assert all(c["n_tokens"] <= 40 for c in chunks)
```

- [ ] **Step 2: Rodar e confirmar que falham**

Run: `pytest tests/test_chunking.py -q`

Expected: erro de coleta com `ModuleNotFoundError: No module named 'jurismatch.chunking'`.

- [ ] **Step 3: Implementar `src/jurismatch/chunking.py`**

```python
"""Empacota blocos (títulos e parágrafos) em chunks com metadados.

Regras: um chunk nunca mistura seções; parágrafos consecutivos são agrupados até o
alvo de tokens; só parágrafos maiores que o teto são quebrados (por sentença).
"""
from __future__ import annotations

import hashlib
import re
from typing import Callable

from jurismatch.config import ALVO_TOKENS, TETO_TOKENS, VERSAO_PIPELINE
from jurismatch.limpeza import MAIUSCULAS, Bloco

ContarTokens = Callable[[str], int]

RE_FIM_SENTENCA = re.compile(rf"(?<=[.!?;])\s+(?=[{MAIUSCULAS}\"“(\d])")
# Abreviações cujo ponto final não encerra a sentença
RE_ABREVIACAO = re.compile(
    r"(?:\b(?:arts?|fls?|n|nº|inc|incs|al|p|pp|cf|v|vol|ed|op|cit|obs|ex|rel|min|des|dr|dra|drs|sr|sra|srs|"
    r"exa|exas|exmo|exma|ilmo|prof|profa|proc|doc|docs|j|julg|dj|dje|i\.e|e\.g)|\b[A-Z])\.$",
    re.IGNORECASE,
)
MAX_SECAO = 120


def dividir_em_sentencas(texto: str) -> list[str]:
    """Divide em sentenças sem quebrar em abreviações jurídicas como 'art.' e 'fls.'."""
    sentencas: list[str] = []
    for parte in RE_FIM_SENTENCA.split(texto):
        if sentencas and RE_ABREVIACAO.search(sentencas[-1]):
            sentencas[-1] += " " + parte
        else:
            sentencas.append(parte)
    return sentencas


def cabecalho(classe: str, numero: int, secao: str) -> str:
    """Contexto prefixado ao chunk antes de embedar: identifica a petição e a seção."""
    base = f"{classe} {numero}"
    return f"{base} | {secao}" if secao else base


def _fatiar(texto: str, limite: int, contar: ContarTokens) -> list[str]:
    """Quebra um texto maior que `limite` em pedaços de sentenças (ou palavras)."""
    pedacos: list[str] = []
    atual = ""
    for sentenca in dividir_em_sentencas(texto):
        if contar(sentenca) > limite:
            unidades = sentenca.split(" ")  # sentença gigante: cai para palavras
        else:
            unidades = [sentenca]
        for unidade in unidades:
            candidato = f"{atual} {unidade}" if atual else unidade
            if atual and contar(candidato) > limite:
                pedacos.append(atual)
                atual = unidade
            else:
                atual = candidato
    if atual:
        pedacos.append(atual)
    return pedacos


def _metodo(metodos: frozenset[str]) -> str:
    return next(iter(metodos)) if len(metodos) == 1 else "misto"


def gerar_chunks(
    blocos: list[Bloco],
    *,
    doc_id: str,
    classe: str,
    numero: int,
    arquivo_pdf: str,
    contar_tokens: ContarTokens,
    alvo: int = ALVO_TOKENS,
    teto: int = TETO_TOKENS,
    indice_inicial: int = 0,
    secao_inicial: str = "",
) -> tuple[list[dict], str]:
    """Devolve (chunks, seção vigente ao final) para os blocos de um arquivo."""
    chunks: list[dict] = []
    secao = secao_inicial
    buffer: list[Bloco] = []
    secao_do_buffer = secao

    def limite_de_texto(s: str) -> int:
        return teto - contar_tokens(cabecalho(classe, numero, s)) - 2

    def tokens_do_buffer() -> int:
        return contar_tokens("\n\n".join(b.texto for b in buffer)) if buffer else 0

    def fechar():
        nonlocal buffer
        if not buffer:
            return
        texto = "\n\n".join(b.texto for b in buffer)
        buffer_atual, buffer = buffer, []
        if sum(c.isalpha() for c in texto) < 20:
            return  # resto de ruído, sem conteúdo
        texto_embedding = f"{cabecalho(classe, numero, secao_do_buffer)}\n{texto}"
        metodos = frozenset().union(*(b.metodos for b in buffer_atual))
        chunks.append(
            {
                "chunk_id": f"{doc_id}_{indice_inicial + len(chunks):04d}",
                "doc_id": doc_id,
                "classe": classe,
                "numero": numero,
                "arquivo_pdf": arquivo_pdf,
                "pagina_inicio": buffer_atual[0].pagina_inicio,
                "pagina_fim": buffer_atual[-1].pagina_fim,
                "metodo_extracao": _metodo(metodos),
                "secao": secao_do_buffer,
                "n_tokens": contar_tokens(texto_embedding),
                "texto": texto,
                "texto_embedding": texto_embedding,
                "hash": hashlib.sha1(texto_embedding.encode("utf-8")).hexdigest(),
                "versao_pipeline": VERSAO_PIPELINE,
            }
        )

    for bloco in blocos:
        if bloco.tipo == "titulo":
            so_titulos = all(b.tipo == "titulo" for b in buffer)
            if not so_titulos or tokens_do_buffer() + contar_tokens(bloco.texto) > alvo:
                fechar()
            secao = bloco.texto[:MAX_SECAO]
            secao_do_buffer = secao
            buffer.append(bloco)
            continue
        if not buffer:
            secao_do_buffer = secao
        limite = limite_de_texto(secao_do_buffer)
        if contar_tokens(bloco.texto) > limite:
            # Parágrafo maior que o teto: fecha o que havia e quebra por sentença
            so_titulos = bool(buffer) and all(b.tipo == "titulo" for b in buffer)
            reserva = tokens_do_buffer() if so_titulos else 0
            if not so_titulos:
                fechar()
            for pedaco in _fatiar(bloco.texto, limite - reserva, contar_tokens):
                buffer.append(
                    Bloco(pedaco, "paragrafo", bloco.pagina_inicio, bloco.pagina_fim, bloco.metodos)
                )
                secao_do_buffer = secao
                fechar()
            continue
        so_titulos = bool(buffer) and all(b.tipo == "titulo" for b in buffer)
        novo_total = contar_tokens("\n\n".join([b.texto for b in buffer] + [bloco.texto]))
        if buffer and (novo_total > limite or (novo_total > alvo and not so_titulos)):
            fechar()
            secao_do_buffer = secao
        buffer.append(bloco)
    fechar()
    return chunks, secao
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `pytest tests/test_chunking.py -q`

Expected: `10 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/jurismatch/chunking.py tests/test_chunking.py
git commit -m "feat: chunking por seção e parágrafo com metadados"
```

---

### Task 6: Pipeline de chunks (CLI) e execução no corpus

**Files:**
- Create: `src/jurismatch/pipeline_chunks.py`
- Test: `tests/test_pipeline_chunks.py`

- [ ] **Step 1: Escrever os testes em `tests/test_pipeline_chunks.py`**

```python
from jurismatch.paginas import Pagina
from jurismatch.pipeline_chunks import paginas_so_com_carimbo, processar_corpus

CARIMBO = (
    "Documento assinado digitalmente conforme MP n° 2.200-2/2001 de 24/08/2001, que institui a "
    "Infra-estrutura de Chaves Públicas Brasileira - ICP-Brasil. O\n"
    "documento pode ser acessado no endereço eletrônico "
    "http://www.stf.jus.br/portal/autenticacao/autenticarDocumento.asp sob o número 400937"
)


def contar(texto):
    return len(texto.split())


def escrever(pasta, nome, paginas):
    corpo = "".join(f"[[pagina {n} | {metodo}]]\n\n{texto}\n\n" for n, metodo, texto in paginas)
    (pasta / nome).write_text(corpo, encoding="utf-8")


def test_paginas_so_com_carimbo():
    paginas = [
        Pagina(1, "nativo", CARIMBO),
        Pagina(2, "nativo", CARIMBO + "\n" + "Texto real da petição. " * 10),
        Pagina(3, "ocr", "x"),
    ]
    assert paginas_so_com_carimbo(paginas) == 1


def test_processar_corpus_junta_partes_e_gera_relatorio(tmp_path):
    escrever(tmp_path, "ADI_10_peticao_inicial_parte01.txt", [
        (1, "nativo", "I. DOS FATOS\n\nA requerente narra os fatos que motivam a presente ação direta."),
    ])
    escrever(tmp_path, "ADI_10_peticao_inicial_parte02.txt", [
        (1, "ocr", "A narrativa continua na segunda parte do arquivo digitalizado."),
    ])
    escrever(tmp_path, "ADC_20_peticao_inicial.txt", [(1, "nativo", CARIMBO), (2, "nativo", CARIMBO)])
    (tmp_path / "log_extracao.csv").write_text("arquivo;paginas\n", encoding="utf-8")

    chunks, relatorio = processar_corpus(tmp_path, contar)

    assert chunks["chunk_id"].tolist() == ["ADI_10_0000", "ADI_10_0001"]
    assert chunks["arquivo_pdf"].tolist() == [
        "ADI_10_peticao_inicial_parte01.pdf",
        "ADI_10_peticao_inicial_parte02.pdf",
    ]
    assert chunks["secao"].tolist() == ["I. DOS FATOS", "I. DOS FATOS"]  # a seção atravessa as partes
    assert chunks["metodo_extracao"].tolist() == ["nativo", "ocr"]
    adc = relatorio.set_index("arquivo").loc["ADC_20_peticao_inicial.txt"]
    assert adc["paginas_so_com_carimbo"] == 2 and adc["chunks"] == 0
```

- [ ] **Step 2: Rodar e confirmar que falham**

Run: `pytest tests/test_pipeline_chunks.py -q`

Expected: erro de coleta com `ModuleNotFoundError: No module named 'jurismatch.pipeline_chunks'`.

- [ ] **Step 3: Implementar `src/jurismatch/pipeline_chunks.py`**

```python
"""Etapa 3: .txt da extração -> dados/chunks.parquet + relatório de qualidade.

Uso: python -m jurismatch.pipeline_chunks
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from jurismatch import config
from jurismatch.chunking import ContarTokens, gerar_chunks
from jurismatch.limpeza import RE_RUIDO, limpar_paginas, montar_blocos, normalizar
from jurismatch.paginas import Pagina, agrupar_por_peticao, ler_paginas


def contador_do_modelo(nome_modelo: str) -> ContarTokens:
    """Conta tokens com o tokenizer do próprio modelo de embedding."""
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(nome_modelo)
    return lambda texto: len(tokenizer.encode(texto, add_special_tokens=False))


def paginas_so_com_carimbo(paginas: list[Pagina]) -> int:
    """Páginas 'nativas' cujo único texto é carimbo de assinatura (faltou OCR na etapa 2)."""
    total = 0
    for pagina in paginas:
        if pagina.metodo != "nativo":
            continue
        linhas = [normalizar(l) for l in pagina.texto.split("\n")]
        bruto = sum(len(l) for l in linhas)
        util = sum(len(l) for l in linhas if not any(r.search(l) for r in RE_RUIDO))
        if bruto >= 100 and util < 100:
            total += 1
    return total


def processar_corpus(dir_txt: Path, contar_tokens: ContarTokens) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devolve (chunks, relatório por arquivo)."""
    chunks: list[dict] = []
    relatorio: list[dict] = []
    for doc_id, arquivos in agrupar_por_peticao(dir_txt).items():
        secao = ""
        inicio_doc = len(chunks)
        for arquivo in arquivos:
            paginas = ler_paginas(arquivo.caminho.read_text(encoding="utf-8"))
            linhas = limpar_paginas(paginas)
            novos, secao = gerar_chunks(
                montar_blocos(linhas),
                doc_id=doc_id,
                classe=arquivo.classe,
                numero=arquivo.numero,
                arquivo_pdf=arquivo.arquivo_pdf,
                contar_tokens=contar_tokens,
                indice_inicial=len(chunks) - inicio_doc,
                secao_inicial=secao,
            )
            chunks.extend(novos)
            linhas_brutas = sum(1 for p in paginas for l in p.texto.split("\n") if l.strip())
            relatorio.append(
                {
                    "arquivo": arquivo.caminho.name,
                    "doc_id": doc_id,
                    "paginas": len(paginas),
                    "paginas_so_com_carimbo": paginas_so_com_carimbo(paginas),
                    "linhas_brutas": linhas_brutas,
                    "linhas_mantidas": sum(1 for l in linhas if l.texto),
                    "chunks": len(novos),
                }
            )
    return pd.DataFrame(chunks), pd.DataFrame(relatorio)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir-txt", type=Path, default=config.DIR_TXT)
    parser.add_argument("--saida", type=Path, default=config.ARQ_CHUNKS)
    parser.add_argument("--modelo", default=config.MODELO_EMBEDDING)
    args = parser.parse_args()

    chunks, relatorio = processar_corpus(args.dir_txt, contador_do_modelo(args.modelo))
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    chunks.to_parquet(args.saida, index=False)
    arq_relatorio = args.saida.with_name("relatorio_chunks.csv")
    relatorio.to_csv(arq_relatorio, index=False, sep=";", encoding="utf-8-sig")

    print(f"{len(chunks)} chunks de {chunks['doc_id'].nunique()} petições -> {args.saida}")
    print(chunks["n_tokens"].describe().round(0).to_string())
    suspeitos = relatorio[(relatorio["paginas_so_com_carimbo"] > 0) | (relatorio["chunks"] == 0)]
    if not suspeitos.empty:
        print("\nATENÇÃO: arquivos que precisam voltar para a etapa 2 (OCR):")
        print(suspeitos[["arquivo", "paginas", "paginas_so_com_carimbo", "chunks"]].to_string(index=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `pytest tests/test_pipeline_chunks.py -q`

Expected: `2 passed`.

- [ ] **Step 5: Rodar o pipeline no corpus real**

Run: `python -m jurismatch.pipeline_chunks`

Na primeira vez baixa o tokenizer do `intfloat/multilingual-e5-base`. Grava `dados/chunks.parquet` e `dados/relatorio_chunks.csv`.

Expected (os números exatos dependem do tokenizer real; no planejamento, com contagem aproximada, foram 7.904 chunks e mediana de 317 tokens):

- primeira linha no formato `N chunks de 95 petições -> .../dados/chunks.parquet`, com N entre 7.000 e 12.000;
- nas estatísticas de `n_tokens`: mediana entre 250 e 400 e `max` até 480 (um chunk de OCR sem espaços pode passar disso; o modelo trunca em 512);
- um bloco `ATENÇÃO` listando `ADI_4271`, `ADI_4376`, `ADI_4393` e `ADI_4966`.

Se aparecerem **outros** arquivos no bloco `ATENÇÃO`, ou menos de 95 petições, pare e relate antes de seguir.

- [ ] **Step 6: Conferir uma amostra a olho**

Run:

```bash
python -c "
import pandas as pd
c = pd.read_parquet('dados/chunks.parquet')
print(c.metodo_extracao.value_counts().to_string())
for i in (5, len(c)//2):
    r = c.iloc[i]; print('\n---', r.chunk_id, 'p.', r.pagina_inicio, '-', r.pagina_fim); print(r.texto_embedding[:500])
"
```

Expected: contagens de `nativo`, `ocr` e alguns `misto`; os dois chunks impressos começam com a linha de cabeçalho (`ADC 100 | II. REQUISITOS FORMAIS...`) e têm parágrafos corridos, sem quebras no meio das frases e sem números de página soltos.

- [ ] **Step 7: Commit**

```bash
git add src/jurismatch/pipeline_chunks.py tests/test_pipeline_chunks.py
git commit -m "feat: pipeline de chunks com relatório de qualidade"
```

---

### Task 7: Índice lexical (BM25 em português)

**Files:**
- Create: `src/jurismatch/lexical.py`
- Test: `tests/test_lexical.py`

- [ ] **Step 1: Escrever os testes em `tests/test_lexical.py`**

```python
from jurismatch.lexical import IndiceLexical, tokenizar


def test_tokenizar_remove_stopwords_e_aplica_stemmer():
    assert tokenizar(["a recuperação judicial das empresas"]) == [["recuper", "judicial", "empres"]]


def test_pontuar_e_persistir(tmp_path):
    textos = ["lei de falências e recuperação judicial", "liberdade de imprensa", "tributo estadual"]
    indice = IndiceLexical.construir(textos)
    scores = indice.pontuar("recuperação judicial de empresas")
    assert scores.shape == (3,)
    assert scores.argmax() == 0 and scores[1] == 0 and scores[2] == 0
    indice.salvar(tmp_path / "bm25")
    recarregado = IndiceLexical.carregar(tmp_path / "bm25")
    assert recarregado.pontuar("imprensa").argmax() == 1
```

- [ ] **Step 2: Rodar e confirmar que falham**

Run: `pytest tests/test_lexical.py -q`

Expected: erro de coleta com `ModuleNotFoundError: No module named 'jurismatch.lexical'`.

- [ ] **Step 3: Implementar `src/jurismatch/lexical.py`**

```python
"""Ramo lexical da busca: BM25 com stopwords e stemmer do português."""
from __future__ import annotations

from pathlib import Path

import bm25s
import numpy as np
import Stemmer

_STEMMER = Stemmer.Stemmer("portuguese")


def tokenizar(textos: list[str]) -> list[list[str]]:
    return bm25s.tokenize(textos, stopwords="pt", stemmer=_STEMMER, return_ids=False, show_progress=False)


class IndiceLexical:
    def __init__(self, bm25: bm25s.BM25):
        self.bm25 = bm25

    @classmethod
    def construir(cls, textos: list[str]) -> "IndiceLexical":
        bm25 = bm25s.BM25()
        bm25.index(tokenizar(textos), show_progress=False)
        return cls(bm25)

    def salvar(self, pasta: Path) -> None:
        self.bm25.save(str(pasta))

    @classmethod
    def carregar(cls, pasta: Path) -> "IndiceLexical":
        return cls(bm25s.BM25.load(str(pasta)))

    def pontuar(self, consulta: str) -> np.ndarray:
        """Score BM25 de todos os chunks, na ordem em que foram indexados."""
        return np.asarray(self.bm25.get_scores(tokenizar([consulta])[0]), dtype="float32")
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `pytest tests/test_lexical.py -q`

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/jurismatch/lexical.py tests/test_lexical.py
git commit -m "feat: índice lexical BM25 com stemmer do português"
```

---

### Task 8: Wrapper do modelo de embedding

**Files:**
- Create: `src/jurismatch/embeddings.py`
- Test: `tests/test_embeddings.py`

- [ ] **Step 1: Escrever o teste em `tests/test_embeddings.py`**

Este teste carrega o modelo real, por isso só roda quando a variável `JURISMATCH_TESTES_LENTOS=1` está definida.

```python
"""Teste lento: baixa o modelo real (~1 GB). Rode com JURISMATCH_TESTES_LENTOS=1."""
import os

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("JURISMATCH_TESTES_LENTOS") != "1", reason="defina JURISMATCH_TESTES_LENTOS=1"
)


def test_embedder_real_normaliza_e_aproxima_textos_relacionados():
    from jurismatch.embeddings import Embedder

    embedder = Embedder()
    passagens = embedder.codificar_passagens(
        ["A liberdade de imprensa veda a censura prévia.", "O ICMS é um imposto estadual."]
    )
    consulta = embedder.codificar_consulta("censura a jornais")
    assert passagens.shape == (2, 768) and passagens.dtype == np.float32
    assert np.allclose(np.linalg.norm(passagens, axis=1), 1.0, atol=1e-4)
    assert passagens[0] @ consulta > passagens[1] @ consulta
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `JURISMATCH_TESTES_LENTOS=1 pytest tests/test_embeddings.py -q`

Expected: FAIL com `ModuleNotFoundError: No module named 'jurismatch.embeddings'`.

- [ ] **Step 3: Implementar `src/jurismatch/embeddings.py`**

```python
"""Wrapper do modelo de embedding: aplica os prefixos e normaliza os vetores."""
from __future__ import annotations

import numpy as np

from jurismatch import config


class Embedder:
    def __init__(
        self,
        nome_modelo: str = config.MODELO_EMBEDDING,
        prefixo_consulta: str = config.PREFIXO_CONSULTA,
        prefixo_passagem: str = config.PREFIXO_PASSAGEM,
    ):
        from sentence_transformers import SentenceTransformer

        self.nome_modelo = nome_modelo
        self.prefixo_consulta = prefixo_consulta
        self.prefixo_passagem = prefixo_passagem
        self.modelo = SentenceTransformer(nome_modelo, device="cpu")
        self.modelo.max_seq_length = 512

    def _codificar(self, textos: list[str], mostrar_progresso: bool) -> np.ndarray:
        vetores = self.modelo.encode(
            textos,
            batch_size=16,
            normalize_embeddings=True,  # com vetores unitários, produto interno = cosseno
            show_progress_bar=mostrar_progresso,
            convert_to_numpy=True,
        )
        return np.asarray(vetores, dtype="float32")

    def codificar_passagens(self, textos: list[str]) -> np.ndarray:
        return self._codificar([self.prefixo_passagem + t for t in textos], mostrar_progresso=True)

    def codificar_consulta(self, consulta: str) -> np.ndarray:
        return self._codificar([self.prefixo_consulta + consulta], mostrar_progresso=False)[0]
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `JURISMATCH_TESTES_LENTOS=1 pytest tests/test_embeddings.py -q`

Na primeira vez baixa o modelo (~1,1 GB) para `~/.cache/huggingface/`.

Expected: `1 passed`. Sem a variável de ambiente o resultado é `1 skipped`.

Este é o único módulo que não foi executado durante o planejamento. Se o teste falhar por diferença de API do sentence-transformers (por exemplo, um argumento de `encode` renomeado), ajuste a chamada em `_codificar` mantendo `normalize_embeddings=True` e a saída `float32`.

- [ ] **Step 5: Commit**

```bash
git add src/jurismatch/embeddings.py tests/test_embeddings.py
git commit -m "feat: wrapper do modelo de embedding com prefixos e5"
```

---

### Task 9: Construção do índice (embeddings + FAISS + BM25)

**Files:**
- Create: `tests/conftest.py`
- Create: `src/jurismatch/indexar.py`
- Test: `tests/test_indexar.py`

- [ ] **Step 1: Criar `tests/conftest.py` com o embedder falso e os chunks de exemplo**

O `EmbedderFalso` tem a mesma interface de `jurismatch.embeddings.Embedder` (`nome_modelo`, `codificar_passagens`, `codificar_consulta`) e permite testar índice e busca sem baixar o modelo.

```python
import hashlib

import numpy as np
import pandas as pd
import pytest

from jurismatch.chunking import gerar_chunks
from jurismatch.limpeza import Bloco


class EmbedderFalso:
    """Embedder determinístico para testes: saco de palavras projetado em 64 dimensões."""

    nome_modelo = "falso-64d"

    def _vetor(self, texto: str) -> np.ndarray:
        v = np.zeros(64, dtype="float32")
        for palavra in texto.lower().split():
            v[int(hashlib.md5(palavra.strip(".,;:").encode()).hexdigest(), 16) % 64] += 1.0
        norma = np.linalg.norm(v)
        return v / norma if norma else v

    def codificar_passagens(self, textos):
        return np.stack([self._vetor(t) for t in textos])

    def codificar_consulta(self, consulta):
        return self._vetor(consulta)


TEXTOS = {
    ("ADI", 1): [
        "A liberdade de imprensa protege as empresas jornalísticas contra a censura prévia.",
        "Pede-se a procedência da ação para declarar a inconstitucionalidade da norma.",
    ],
    ("ADI", 2): [
        "O imposto estadual sobre circulação de mercadorias viola a legalidade tributária.",
        "Pede-se a procedência da ação para declarar a inconstitucionalidade da norma.",
    ],
    ("ADC", 3): [
        "A recuperação judicial e a falência seguem a Lei 11.101/2005, cuja validade se afirma.",
    ],
}


@pytest.fixture
def embedder_falso():
    return EmbedderFalso()


@pytest.fixture
def chunks_exemplo():
    linhas = []
    for (classe, numero), paragrafos in TEXTOS.items():
        blocos = [Bloco(p, "paragrafo", i + 1, i + 1, frozenset({"nativo"})) for i, p in enumerate(paragrafos)]
        novos, _ = gerar_chunks(
            blocos, doc_id=f"{classe}_{numero}", classe=classe, numero=numero,
            arquivo_pdf=f"{classe}_{numero}_peticao_inicial.pdf",
            contar_tokens=lambda t: len(t.split()), alvo=5, teto=60,
        )
        linhas.extend(novos)
    return pd.DataFrame(linhas)
```

- [ ] **Step 2: Escrever os testes em `tests/test_indexar.py`**

```python
import json

import faiss
import numpy as np
import pandas as pd

from jurismatch.indexar import construir_indice


def test_construir_indice_grava_artefatos_alinhados(tmp_path, chunks_exemplo, embedder_falso):
    construir_indice(chunks_exemplo, embedder_falso, tmp_path)
    indice = faiss.read_index(str(tmp_path / "faiss.index"))
    salvos = pd.read_parquet(tmp_path / "chunks.parquet")
    manifesto = json.loads((tmp_path / "manifesto.json").read_text())
    assert indice.ntotal == len(salvos) == len(chunks_exemplo) == manifesto["n_chunks"]
    assert manifesto["modelo"] == "falso-64d" and manifesto["dimensao"] == 64
    assert manifesto["n_peticoes"] == 3
    assert (tmp_path / "bm25").is_dir()
    vetores = np.load(tmp_path / "embeddings.npy")
    assert np.allclose(np.linalg.norm(vetores, axis=1), 1.0, atol=1e-5)


def test_construir_indice_reaproveita_embeddings(tmp_path, chunks_exemplo, embedder_falso):
    construir_indice(chunks_exemplo, embedder_falso, tmp_path)
    chamadas = []
    original = embedder_falso.codificar_passagens
    embedder_falso.codificar_passagens = lambda textos: chamadas.append(len(textos)) or original(textos)
    construir_indice(chunks_exemplo, embedder_falso, tmp_path)
    assert chamadas == []  # nada mudou: nenhum embedding recalculado
```

- [ ] **Step 3: Rodar e confirmar que falham**

Run: `pytest tests/test_indexar.py -q`

Expected: erro de coleta com `ModuleNotFoundError: No module named 'jurismatch.indexar'`.

- [ ] **Step 4: Implementar `src/jurismatch/indexar.py`**

```python
"""Etapa 4: dados/chunks.parquet -> dados/indice/ (FAISS + BM25 + metadados).

Uso: python -m jurismatch.indexar
A linha i de chunks.parquet corresponde ao vetor i do índice FAISS e ao documento i do BM25.
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import faiss
import numpy as np
import pandas as pd

from jurismatch import config
from jurismatch.lexical import IndiceLexical


def carregar_cache(dir_indice: Path, nome_modelo: str) -> dict[str, np.ndarray]:
    """Vetores já calculados com o mesmo modelo, por hash do texto embedado."""
    manifesto = dir_indice / "manifesto.json"
    if not manifesto.exists() or json.loads(manifesto.read_text())["modelo"] != nome_modelo:
        return {}
    hashes = pd.read_parquet(dir_indice / "chunks.parquet", columns=["hash"])["hash"]
    vetores = np.load(dir_indice / "embeddings.npy")
    return dict(zip(hashes, vetores))


def construir_indice(chunks: pd.DataFrame, embedder, dir_indice: Path) -> None:
    """Gera embeddings (reaproveitando o cache), índice FAISS exato e índice BM25."""
    cache = carregar_cache(dir_indice, embedder.nome_modelo)
    faltam = chunks[~chunks["hash"].isin(cache.keys())].drop_duplicates("hash")
    print(f"{len(chunks)} chunks; {len(faltam)} embeddings a calcular")
    if len(faltam):
        novos = embedder.codificar_passagens(faltam["texto_embedding"].tolist())
        cache.update(zip(faltam["hash"], novos))
    vetores = np.stack([cache[h] for h in chunks["hash"]]).astype("float32")

    dir_indice.mkdir(parents=True, exist_ok=True)
    indice = faiss.IndexFlatIP(vetores.shape[1])  # busca exata por produto interno
    indice.add(vetores)
    faiss.write_index(indice, str(dir_indice / "faiss.index"))
    np.save(dir_indice / "embeddings.npy", vetores)

    pasta_bm25 = dir_indice / "bm25"
    if pasta_bm25.exists():
        shutil.rmtree(pasta_bm25)
    IndiceLexical.construir(chunks["texto"].tolist()).salvar(pasta_bm25)

    chunks.reset_index(drop=True).to_parquet(dir_indice / "chunks.parquet", index=False)
    manifesto = {
        "modelo": embedder.nome_modelo,
        "dimensao": int(vetores.shape[1]),
        "n_chunks": int(len(chunks)),
        "n_peticoes": int(chunks["doc_id"].nunique()),
        "versao_pipeline": str(chunks["versao_pipeline"].iloc[0]),
        "criado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (dir_indice / "manifesto.json").write_text(json.dumps(manifesto, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=config.ARQ_CHUNKS)
    parser.add_argument("--dir-indice", type=Path, default=config.DIR_INDICE)
    parser.add_argument("--modelo", default=config.MODELO_EMBEDDING)
    args = parser.parse_args()

    from jurismatch.embeddings import Embedder

    construir_indice(pd.read_parquet(args.chunks), Embedder(args.modelo), args.dir_indice)
    print(f"Índice gravado em {args.dir_indice}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Rodar e confirmar que passam**

Run: `pytest tests/test_indexar.py -q`

Expected: `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py src/jurismatch/indexar.py tests/test_indexar.py
git commit -m "feat: construção do índice FAISS exato + BM25 com cache de embeddings"
```

---

### Task 10: Busca híbrida com ranking de petições

**Files:**
- Create: `src/jurismatch/busca.py`
- Test: `tests/test_busca.py`

- [ ] **Step 1: Escrever os testes em `tests/test_busca.py`**

```python
import pandas as pd
import pytest

from jurismatch.busca import Buscador, posicoes, rrf
from jurismatch.indexar import construir_indice


def test_posicoes_ignora_score_zero():
    r = posicoes(pd.Series({"a": 0.2, "b": 0.9, "c": 0.0}))
    assert r["b"] == 1 and r["a"] == 2 and pd.isna(r["c"])


def test_rrf_soma_inversos_das_posicoes():
    r1 = pd.Series({"a": 1.0, "b": 2.0})
    r2 = pd.Series({"a": 2.0, "b": float("nan")})
    fundido = rrf([r1, r2], k=60)
    assert fundido["a"] == pytest.approx(1 / 61 + 1 / 62)
    assert fundido["b"] == pytest.approx(1 / 62)


@pytest.fixture
def buscador(tmp_path, chunks_exemplo, embedder_falso):
    construir_indice(chunks_exemplo, embedder_falso, tmp_path)
    return Buscador(tmp_path, embedder=embedder_falso)


@pytest.mark.parametrize("modo", ["hibrido", "denso", "lexical"])
def test_buscar_devolve_a_peticao_certa_em_primeiro(buscador, modo):
    resultados = buscador.buscar("liberdade de imprensa e censura", k=3, modo=modo)
    assert resultados[0]["doc_id"] == "ADI_1"
    assert "imprensa" in resultados[0]["trecho"]
    assert resultados[0]["pagina"] == 1
    assert resultados[0]["link_pdf"].endswith("ADI_1_peticao_inicial.pdf#page=1")


def test_buscar_devolve_uma_linha_por_peticao(buscador):
    resultados = buscador.buscar("procedência da ação inconstitucionalidade da norma", k=10)
    docs = [r["doc_id"] for r in resultados]
    assert len(docs) == len(set(docs))
    assert [r["posicao"] for r in resultados] == list(range(1, len(resultados) + 1))


def test_buscar_termo_exato_de_lei_no_lexical(buscador):
    resultados = buscador.buscar("Lei 11.101/2005", k=1, modo="lexical")
    assert resultados[0]["doc_id"] == "ADC_3"


def test_buscar_filtra_por_classe(buscador):
    resultados = buscador.buscar("inconstitucionalidade da norma e validade da falência", k=10, classe="ADC")
    assert {r["classe"] for r in resultados} == {"ADC"}


def test_buscar_modo_invalido(buscador):
    with pytest.raises(ValueError):
        buscador.buscar("x", modo="outro")
```

- [ ] **Step 2: Rodar e confirmar que falham**

Run: `pytest tests/test_busca.py -q`

Expected: erro de coleta com `ModuleNotFoundError: No module named 'jurismatch.busca'`.

- [ ] **Step 3: Implementar `src/jurismatch/busca.py`**

Fluxo de `buscar`: calcula o score de **todos** os chunks em cada sistema (denso e lexical); reduz a um score por petição com o máximo (MaxP); transforma em posições e funde com RRF; para cada petição do topo, escolhe como trecho o chunk com melhor RRF em nível de chunk. Chunks com score BM25 igual a zero não entram no ranking lexical.

```python
"""Busca: consulta -> ranking de petições, cada uma com seu melhor trecho.

Uso: python -m jurismatch.busca "consulta" [--k 5] [--modo hibrido|denso|lexical] [--classe ADI]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import faiss
import numpy as np
import pandas as pd

from jurismatch import config
from jurismatch.lexical import IndiceLexical

MODOS = ("hibrido", "denso", "lexical")


def posicoes(scores: pd.Series) -> pd.Series:
    """Posição no ranking (1 = melhor). Score <= 0 ou ausente fica sem posição (NaN)."""
    validos = scores[scores > 0]
    return validos.rank(method="first", ascending=False).reindex(scores.index)


def rrf(rankings: list[pd.Series], k: int = config.RRF_K) -> pd.Series:
    """Reciprocal Rank Fusion: soma de 1/(k + posição) em cada ranking."""
    total = None
    for r in rankings:
        parcela = (1.0 / (k + r)).fillna(0.0)
        total = parcela if total is None else total.add(parcela, fill_value=0.0)
    return total


class Buscador:
    def __init__(self, dir_indice: Path = config.DIR_INDICE, embedder=None):
        self.chunks = pd.read_parquet(dir_indice / "chunks.parquet")
        self.faiss = faiss.read_index(str(dir_indice / "faiss.index"))
        self.lexical = IndiceLexical.carregar(dir_indice / "bm25")
        self._embedder = embedder
        if self.faiss.ntotal != len(self.chunks):
            raise ValueError("Índice FAISS e chunks.parquet estão desalinhados; rode jurismatch.indexar")

    @property
    def embedder(self):
        if self._embedder is None:
            from jurismatch.embeddings import Embedder

            self._embedder = Embedder()
        return self._embedder

    def _scores_densos(self, consulta: str) -> np.ndarray:
        """Similaridade (cosseno) da consulta com todos os chunks — busca exata."""
        vetor = self.embedder.codificar_consulta(consulta).reshape(1, -1)
        distancias, indices = self.faiss.search(vetor, self.faiss.ntotal)
        scores = np.zeros(self.faiss.ntotal, dtype="float32")
        scores[indices[0]] = distancias[0]
        return scores

    def buscar(self, consulta: str, k: int = 10, modo: str = "hibrido", classe: str | None = None) -> list[dict]:
        if modo not in MODOS:
            raise ValueError(f"modo deve ser um de {MODOS}")
        tabela = self.chunks[["doc_id"]].copy()
        colunas = []
        if modo in ("hibrido", "denso"):
            tabela["denso"] = self._scores_densos(consulta)
            colunas.append("denso")
        if modo in ("hibrido", "lexical"):
            tabela["lexical"] = self.lexical.pontuar(consulta)
            colunas.append("lexical")
        if classe:
            tabela = tabela[self.chunks["classe"] == classe]

        # 1) MaxP: a petição vale o seu melhor chunk, em cada sistema
        por_doc = tabela.groupby("doc_id")[colunas].max()
        # 2) RRF sobre os rankings de petições
        score_doc = rrf([posicoes(por_doc[c]) for c in colunas])
        score_doc = score_doc[score_doc > 0].sort_values(ascending=False, kind="stable").head(k)
        # 3) Melhor trecho de cada petição: RRF sobre os rankings de chunks
        score_chunk = rrf([posicoes(tabela[c]) for c in colunas])

        resultados = []
        for posicao, (doc_id, score) in enumerate(score_doc.items(), start=1):
            do_doc = score_chunk[tabela["doc_id"] == doc_id]
            chunk = self.chunks.loc[do_doc.idxmax()]
            resultados.append(
                {
                    "posicao": posicao,
                    "doc_id": doc_id,
                    "classe": chunk["classe"],
                    "numero": int(chunk["numero"]),
                    "score": float(score),
                    "chunk_id": chunk["chunk_id"],
                    "secao": chunk["secao"],
                    "trecho": chunk["texto"],
                    "arquivo_pdf": chunk["arquivo_pdf"],
                    "pagina": int(chunk["pagina_inicio"]),
                    "link_pdf": f"{(config.DIR_PDF / chunk['arquivo_pdf']).as_posix()}#page={int(chunk['pagina_inicio'])}",
                    "metodo_extracao": chunk["metodo_extracao"],
                }
            )
        return resultados


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("consulta")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--modo", choices=MODOS, default="hibrido")
    parser.add_argument("--classe", choices=("ADI", "ADC"))
    parser.add_argument("--dir-indice", type=Path, default=config.DIR_INDICE)
    args = parser.parse_args()

    for r in Buscador(args.dir_indice).buscar(args.consulta, k=args.k, modo=args.modo, classe=args.classe):
        print(f"\n{r['posicao']}. {r['classe']} {r['numero']}  (score {r['score']:.4f})")
        print(f"   {r['arquivo_pdf']}, p. {r['pagina']} [{r['metodo_extracao']}]  {r['secao']}")
        print(f"   {r['trecho'][:400].replace(chr(10), ' ')}...")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `pytest tests/test_busca.py -q`

Expected: `9 passed`.

- [ ] **Step 5: Rodar a suíte inteira**

Run: `pytest -q`

Expected: `44 passed, 1 skipped`.

- [ ] **Step 6: Commit**

```bash
git add src/jurismatch/busca.py tests/test_busca.py
git commit -m "feat: busca híbrida com MaxP por petição e fusão RRF"
```

---

### Task 11: Indexar o corpus, validar ponta a ponta e documentar

**Files:**
- Modify: `README.md` (substituir o conteúdo)

- [ ] **Step 1: Construir o índice do corpus real**

Run: `python -m jurismatch.indexar`

Calcula os embeddings em CPU (pode levar de dezenas de minutos a mais de uma hora; uma barra de progresso é exibida) e grava `dados/indice/`. Se for interrompido antes do fim, nada é salvo e é preciso rodar de novo; depois de concluído, novas execuções reaproveitam os vetores pelo `hash`.

Expected: `N chunks; N embeddings a calcular` (ou um pouco menos, porque chunks idênticos são embedados uma vez), a barra de progresso e, ao final, `Índice gravado em .../dados/indice`.

- [ ] **Step 2: Conferir os artefatos**

Run: `python -c "import json, faiss; m=json.load(open('dados/indice/manifesto.json')); i=faiss.read_index('dados/indice/faiss.index'); print(m); print(i.ntotal == m['n_chunks'], i.d)"`

Expected: o manifesto com `"modelo": "intfloat/multilingual-e5-base"`, `"dimensao": 768`, `"n_peticoes": 95`; depois `True 768`.

- [ ] **Step 3: Validar com consultas de resposta conhecida**

Run:

```bash
python -m jurismatch.busca "participação de capital estrangeiro em empresas jornalísticas e portais de notícias" --k 3
python -m jurismatch.busca "responsabilidade do investidor por dívidas da empresa em recuperação judicial" --k 3
python -m jurismatch.busca "Lei 11.101/2005" --k 3 --modo lexical
python -m jurismatch.busca "decreto legislativo que sustou o aumento do IOF" --k 3 --classe ADC
```

Expected: `ADI 5613` em 1º na primeira consulta e `ADC 100` em 1º na segunda e na terceira (confirmado no modo lexical durante o planejamento; no híbrido devem aparecer no top 3). Na quarta, só ADCs, com `ADC 96` e/ou `ADC 97` no top 3. Cada resultado mostra arquivo PDF, página, método de extração e o início do trecho.

Se alguma petição esperada não aparecer no top 3, **não ajuste parâmetros**: registre a consulta e o resultado no relato final. Calibrar a busca é trabalho do plano de avaliação.

- [ ] **Step 4: Substituir o conteúdo de `README.md`**

````markdown
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
````

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: README com pipeline, stack e limitações"
```

- [ ] **Step 6: Relato final**

Informe à Julia: número de chunks e de petições, mediana e máximo de `n_tokens`, tempo gasto nos embeddings, os arquivos listados no bloco `ATENÇÃO` do pipeline e o resultado das quatro consultas de validação. Lembre que nada foi enviado ao remoto (`git push` não faz parte deste plano).

---
