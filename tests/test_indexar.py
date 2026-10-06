import json

import faiss
import numpy as np
import pandas as pd

from jurismatch.indexar import construir_indice


def test_construir_indice_grava_artefatos_alinhados(tmp_path, chunks_exemplo, embedder_falso):
    construir_indice(chunks_exemplo, embedder_falso, tmp_path)
    indice = faiss.read_index(str(tmp_path / "faiss.index"))
    salvos = pd.read_parquet(tmp_path / "chunks.parquet")
    manifesto = json.loads((tmp_path / "manifesto.json").read_text())
    assert indice.ntotal == len(salvos) == len(chunks_exemplo) == manifesto["n_chunks"]
    assert manifesto["modelo"] == "falso-64d" and manifesto["dimensao"] == 64
    assert manifesto["n_peticoes"] == 3
    assert (tmp_path / "bm25").is_dir()
    vetores = np.load(tmp_path / "embeddings.npy")
    assert np.allclose(np.linalg.norm(vetores, axis=1), 1.0, atol=1e-5)


def test_construir_indice_reaproveita_embeddings(tmp_path, chunks_exemplo, embedder_falso):
    construir_indice(chunks_exemplo, embedder_falso, tmp_path)
    chamadas = []
    original = embedder_falso.codificar_passagens
    embedder_falso.codificar_passagens = lambda textos: chamadas.append(len(textos)) or original(textos)
    construir_indice(chunks_exemplo, embedder_falso, tmp_path)
    assert chamadas == []  # nada mudou: nenhum embedding recalculado
