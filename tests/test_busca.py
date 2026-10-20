import numpy as np
import pandas as pd
import pytest

from jurismatch.busca import Buscador, posicoes, rrf
from jurismatch.indexar import construir_indice


def test_posicoes_ignora_score_zero():
    r = posicoes(pd.Series({"a": 0.2, "b": 0.9, "c": 0.0}))
    assert r["b"] == 1 and r["a"] == 2 and pd.isna(r["c"])


def test_rrf_soma_inversos_das_posicoes():
    r1 = pd.Series({"a": 1.0, "b": 2.0})
    r2 = pd.Series({"a": 2.0, "b": float("nan")})
    fundido = rrf([r1, r2], k=60)
    assert fundido["a"] == pytest.approx(1 / 61 + 1 / 62)
    assert fundido["b"] == pytest.approx(1 / 62)


@pytest.fixture
def buscador(tmp_path, chunks_exemplo, embedder_falso):
    construir_indice(chunks_exemplo, embedder_falso, tmp_path)
    return Buscador(tmp_path, embedder=embedder_falso)


@pytest.mark.parametrize("modo", ["hibrido", "denso", "lexical"])
def test_buscar_devolve_a_peticao_certa_em_primeiro(buscador, modo):
    resultados = buscador.buscar("liberdade de imprensa e censura", k=3, modo=modo)
    assert resultados[0]["doc_id"] == "ADI_1"
    assert "imprensa" in resultados[0]["trecho"]
    assert resultados[0]["pagina"] == 1
    assert resultados[0]["link_pdf"].endswith("ADI_1_peticao_inicial.pdf#page=1")


def test_buscar_devolve_uma_linha_por_peticao(buscador):
    resultados = buscador.buscar("procedência da ação inconstitucionalidade da norma", k=10)
    docs = [r["doc_id"] for r in resultados]
    assert len(docs) == len(set(docs))
    assert [r["posicao"] for r in resultados] == list(range(1, len(resultados) + 1))


def test_buscar_termo_exato_de_lei_no_lexical(buscador):
    resultados = buscador.buscar("Lei 11.101/2005", k=1, modo="lexical")
    assert resultados[0]["doc_id"] == "ADC_3"


def test_buscar_filtra_por_classe(buscador):
    resultados = buscador.buscar("inconstitucionalidade da norma e validade da falência", k=10, classe="ADC")
    assert {r["classe"] for r in resultados} == {"ADC"}


class RerankerFalso:
    """Nota 0.9 para trechos que contêm 'imprensa', 0.1 para os demais."""

    def pontuar(self, consulta, textos):
        return np.array([0.9 if "imprensa" in t else 0.1 for t in textos], dtype="float32")


@pytest.fixture
def buscador_rerank(tmp_path, chunks_exemplo, embedder_falso):
    construir_indice(chunks_exemplo, embedder_falso, tmp_path)
    return Buscador(tmp_path, embedder=embedder_falso, reranker=RerankerFalso())


def test_rerank_descarta_peticoes_abaixo_do_limiar(buscador_rerank):
    resultados = buscador_rerank.buscar("liberdade de imprensa e censura", k=10, rerank=True, limiar=0.6)
    assert [r["doc_id"] for r in resultados] == ["ADI_1"]
    assert resultados[0]["score"] == pytest.approx(0.9)
    assert "imprensa" in resultados[0]["trecho"]


def test_rerank_sem_resultado_relevante_devolve_lista_vazia(buscador_rerank):
    assert buscador_rerank.buscar("Lei 11.101/2005", k=10, rerank=True, limiar=0.95) == []


def test_rerank_limiar_zero_mantem_uma_linha_por_peticao(buscador_rerank):
    resultados = buscador_rerank.buscar("procedência da ação inconstitucionalidade da norma", k=10, rerank=True, limiar=0.0)
    docs = [r["doc_id"] for r in resultados]
    assert len(docs) == len(set(docs)) > 1
    assert [r["score"] for r in resultados] == sorted((r["score"] for r in resultados), reverse=True)


def test_buscar_modo_invalido(buscador):
    with pytest.raises(ValueError):
        buscador.buscar("x", modo="outro")
