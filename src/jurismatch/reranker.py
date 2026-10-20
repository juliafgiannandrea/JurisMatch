"""Wrapper do cross-encoder: pontua pares (consulta, trecho) com uma nota de relevância em [0, 1]."""
from __future__ import annotations

import numpy as np

from jurismatch import config


class Reranker:
    def __init__(self, nome_modelo: str = config.MODELO_RERANKER):
        import torch
        from sentence_transformers import CrossEncoder

        self.nome_modelo = nome_modelo
        # Sigmoide explícita: alguns modelos devolvem logits, e o limiar precisa de notas em [0, 1]
        self.modelo = CrossEncoder(
            nome_modelo, device="cpu", max_length=512, activation_fn=torch.nn.Sigmoid()
        )

    def pontuar(self, consulta: str, textos: list[str]) -> np.ndarray:
        if not textos:
            return np.zeros(0, dtype="float32")
        notas = self.modelo.predict([(consulta, t) for t in textos], batch_size=8, show_progress_bar=False)
        return np.asarray(notas, dtype="float32")
