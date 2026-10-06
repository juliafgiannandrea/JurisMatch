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
