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
