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
