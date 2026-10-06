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


def test_buscar_modo_invalido(buscador):
    with pytest.raises(ValueError):
        buscador.buscar("x", modo="outro")
