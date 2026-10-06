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
