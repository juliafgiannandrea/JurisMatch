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
ARQ_DOCUMENTOS = DIR_METADATA / "documentos.csv"

# Índices de busca: FAISS + BM25 + cópia dos chunks + manifesto (04_index)
DIR_INDICE = RAIZ / "vectorstore"

# Embeddings: multilingual-e5 exige os prefixos abaixo (ver card do modelo)
MODELO_EMBEDDING = "intfloat/multilingual-e5-base"
PREFIXO_CONSULTA = "query: "
PREFIXO_PASSAGEM = "passage: "

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
