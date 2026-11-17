import pandas as pd

from jurismatch.classificacao import carregar_legislacao, classificar_corpus, classificar_peticao

PAGINA_MP = "Impugna-se a Medida Provisória nº 1.045, de 2021, e a MP 936."
PAGINA_NEUTRA = "Da legitimidade ativa do partido político com representação no Congresso Nacional."


def test_texto_com_mencoes_suficientes_e_mp():
    r = classificar_peticao([PAGINA_MP, PAGINA_MP])  # 4 menções nas primeiras páginas
    assert r["impugna_mp"] is True and r["fonte_mp"] == "texto" and r["mencoes_mp"] == 4


def test_texto_com_poucas_mencoes_nao_e_mp():
    r = classificar_peticao(["Cita-se a Medida Provisória nº 2.200-2/2001 sobre assinatura digital.", PAGINA_NEUTRA])
    assert r["impugna_mp"] is False and r["mencoes_mp"] == 1


def test_mencoes_depois_das_primeiras_paginas_nao_contam():
    paginas = [PAGINA_NEUTRA] * 10 + [PAGINA_MP] * 5
    assert classificar_peticao(paginas)["impugna_mp"] is False


def test_legislacao_com_mp_exige_ao_menos_uma_mencao_no_texto():
    leg = "1 - Medida Provisória nº 1045 de 2021"
    assert classificar_peticao(["Impugna-se a Medida Provisória nº 1.045."], leg)["impugna_mp"] is True
    assert classificar_peticao([PAGINA_NEUTRA], leg)["impugna_mp"] is False


def test_legislacao_sem_mp_prevalece_sobre_o_texto():
    r = classificar_peticao([PAGINA_MP] * 3, "1 - Lei Federal nº 6404 de 1976")
    assert r["impugna_mp"] is False and r["fonte_mp"] == "legislacao"


def test_pedido_liminar():
    assert classificar_peticao([PAGINA_NEUTRA, "Requer a concessão de medida cautelar."])["pedido_liminar"] is True
    assert classificar_peticao([PAGINA_NEUTRA, "Pede-se a tutela de urgência."])["pedido_liminar"] is True
    assert classificar_peticao([PAGINA_NEUTRA])["pedido_liminar"] is False


def test_classificar_corpus_junta_as_partes_da_peticao(tmp_path):
    pagina = lambda n, t: f"[[pagina {n} | nativo]]\n{t}\n"  # noqa: E731
    (tmp_path / "ADI_10_peticao_inicial_parte01.txt").write_text(pagina(1, PAGINA_MP), encoding="utf-8")
    (tmp_path / "ADI_10_peticao_inicial_parte02.txt").write_text(pagina(1, "Requer liminar. " + PAGINA_MP), encoding="utf-8")
    (tmp_path / "ADPF_20_peticao_inicial.txt").write_text(pagina(1, PAGINA_NEUTRA), encoding="utf-8")
    tabela = classificar_corpus(tmp_path).set_index("doc_id")
    assert tabela.loc["ADI_10", "impugna_mp"] and tabela.loc["ADI_10", "pedido_liminar"]
    assert not tabela.loc["ADPF_20", "impugna_mp"] and not tabela.loc["ADPF_20", "pedido_liminar"]


def test_classificar_corpus_usa_a_legislacao_do_doc(tmp_path):
    (tmp_path / "ADI_10_peticao_inicial.txt").write_text(f"[[pagina 1 | nativo]]\n{PAGINA_MP}\n", encoding="utf-8")
    tabela = classificar_corpus(tmp_path, {"ADI_10": "Lei Estadual nº 1"})
    assert tabela.loc[0, "fonte_mp"] == "legislacao" and not tabela.loc[0, "impugna_mp"]


def test_carregar_legislacao(tmp_path):
    planilha = tmp_path / "base.xlsx"
    pd.DataFrame({"Processo": ["ADI 10", "ADC 3"], "Legislação": ["Medida Provisória nº 1", None]}).to_excel(planilha, index=False)
    assert carregar_legislacao(planilha) == {"ADI_10": "Medida Provisória nº 1"}
    assert carregar_legislacao(tmp_path / "nao_existe.xlsx") == {}
