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

# Reranker (cross-encoder): reavalia os melhores chunks da busca híbrida com notas em [0, 1].
# bge-reranker-v2-m3 é bem calibrado, mas leva ~1 s por chunk em CPU; para algo mais rápido e
# menos calibrado, "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1" (~0,1 s por chunk).
MODELO_RERANKER = "BAAI/bge-reranker-v2-m3"
CANDIDATOS_RERANK = 30  # chunks enviados ao reranker
LIMIAR_RERANK = 0.8  # petições cujo melhor chunk fica abaixo disso são descartadas

# Mude este valor sempre que a limpeza ou o chunking mudarem de comportamento
VERSAO_PIPELINE = "1"
