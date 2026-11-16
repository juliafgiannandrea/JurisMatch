"""Wrapper do modelo de embedding: aplica os prefixos e normaliza os vetores."""
from __future__ import annotations

import numpy as np

from jurismatch import config


class Embedder:
    def __init__(
        self,
        nome_modelo: str = config.MODELO_EMBEDDING,
        prefixo_consulta: str | None = None,
        prefixo_passagem: str | None = None,
        device: str | None = None,
    ):
        import torch
        from sentence_transformers import SentenceTransformer

        padrao_consulta, padrao_passagem = config.prefixos(nome_modelo)
        self.nome_modelo = nome_modelo
        self.prefixo_consulta = padrao_consulta if prefixo_consulta is None else prefixo_consulta
        self.prefixo_passagem = padrao_passagem if prefixo_passagem is None else prefixo_passagem
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.modelo = SentenceTransformer(nome_modelo, device=self.device)
        self.modelo.max_seq_length = 512  # os chunks têm até TETO_TOKENS (480); contexto maior só deixaria mais lento

    def _codificar(self, textos: list[str], mostrar_progresso: bool) -> np.ndarray:
        vetores = self.modelo.encode(
            textos,
            batch_size=64 if self.device == "cuda" else 16,
            normalize_embeddings=True,  # com vetores unitários, produto interno = cosseno
            show_progress_bar=mostrar_progresso,
            convert_to_numpy=True,
        )
        return np.asarray(vetores, dtype="float32")

    def codificar_passagens(self, textos: list[str]) -> np.ndarray:
        return self._codificar([self.prefixo_passagem + t for t in textos], mostrar_progresso=True)

    def codificar_consulta(self, consulta: str) -> np.ndarray:
        return self._codificar([self.prefixo_consulta + consulta], mostrar_progresso=False)[0]
