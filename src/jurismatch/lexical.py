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
