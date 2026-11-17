"""Caminhos e parâmetros do projeto. Único lugar onde eles são definidos."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

# Dados, na ordem do pipeline (ver "Estrutura de pastas" no README)
DIR_DATA = RAIZ / "data"
DIR_PDF = DIR_DATA / "01_raw" / "pdf"  # PDFs baixados do STF
DIR_OCR = DIR_DATA / "02_processed" / "ocr"  # 01_ocr: texto extraído, com marcadores de página
DIR_CLEAN = DIR_DATA / "02_processed" / "clean"  # 02_clean: texto limpo, mesmo formato
DIR_CHUNKS = DIR_DATA / "03_chunks"  # 03_chunk: trechos com metadados
ARQ_CHUNKS = DIR_CHUNKS / "chunks.parquet"
ARQ_RELATORIO_LIMPEZA = DIR_CLEAN / "relatorio_limpeza.csv"
ARQ_RELATORIO_CHUNKS = DIR_CHUNKS / "relatorio_chunks.csv"

# Uma linha por petição (gerado por 03_chunk)
DIR_METADATA = RAIZ / "metadata"
# Planilha base do STF: a coluna Legislação ajuda a classificar a norma impugnada (classificacao.py)
ARQ_PLANILHA_BASE = RAIZ / "scrapping_processos_controle_concentrado" / "base_inicial_controle_concentrado_stf_2026_09_08.xlsx"
ARQ_DOCUMENTOS = DIR_METADATA / "documentos.csv"

# Link oficial do processo no portal do STF (incidente vem do log de download dos PDFs)
ARQ_INCIDENTES = DIR_PDF / "log_download.csv"
URL_PROCESSO_STF = "https://portal.stf.jus.br/processos/detalhe.asp?incidente={incidente}"

# Índices de busca: FAISS + BM25 + cópia dos chunks + manifesto (04_index)
DIR_INDICE = RAIZ / "vectorstore"

# PWA estático servido pela API (python -m jurismatch.api)
DIR_WEB = RAIZ / "app" / "web"

# Embeddings. A busca usa o modelo gravado no manifesto do índice, não este padrão.
MODELO_EMBEDDING = "intfloat/multilingual-e5-base"
# Alternativa testada: "Qwen/Qwen3-Embedding-0.6B" (~2,4 GB de RAM, mais lento em CPU)

# Cada modelo espera um texto antes da consulta e da passagem (ver o card de cada um no Hugging Face).
INSTRUCAO_BUSCA = "Dada uma consulta, encontre trechos de petições iniciais do STF relevantes para ela"
PREFIXOS_POR_MODELO = {  # trecho do nome do modelo -> (prefixo da consulta, prefixo da passagem)
    "multilingual-e5-large-instruct": (f"Instruct: {INSTRUCAO_BUSCA}\nQuery: ", ""),
    "multilingual-e5": ("query: ", "passage: "),
    "Qwen3-Embedding": (f"Instruct: {INSTRUCAO_BUSCA}\nQuery:", ""),
}


def prefixos(nome_modelo: str) -> tuple[str, str]:
    """(prefixo da consulta, prefixo da passagem); modelos fora da tabela (ex.: bge-m3) não usam prefixo."""
    for trecho, par in PREFIXOS_POR_MODELO.items():
        if trecho in nome_modelo:
            return par
    return ("", "")

# Chunking: alvo de tokens por chunk e teto rígido (o modelo trunca em 512)
ALVO_TOKENS = 350
TETO_TOKENS = 480

# Fusão híbrida (Reciprocal Rank Fusion). Não confundir com o --k da busca (nº de petições).
RRF_K = 60

# Reranker (cross-encoder): reavalia os melhores chunks da busca híbrida com notas em [0, 1].
# bge-reranker-v2-m3 é bem calibrado, mas leva ~1 s por chunk em CPU; para algo mais rápido e
# menos calibrado, "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1" (~0,1 s por chunk).
MODELO_RERANKER = "BAAI/bge-reranker-v2-m3"
CANDIDATOS_RERANK = 30  # chunks enviados ao reranker
LIMIAR_RERANK = 0.8  # petições cujo melhor chunk fica abaixo disso são descartadas

# Mude este valor sempre que a limpeza ou o chunking mudarem de comportamento
VERSAO_PIPELINE = "1"
