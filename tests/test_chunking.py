from jurismatch.chunking import cabecalho, dividir_em_sentencas, gerar_chunks
from jurismatch.limpeza import Bloco


def contar(texto):
    return len(texto.split())


def P(texto, pag_ini=1, pag_fim=None, metodo="nativo"):
    return Bloco(texto, "paragrafo", pag_ini, pag_fim or pag_ini, frozenset({metodo}))


def T(texto, pag=1):
    return Bloco(texto, "titulo", pag, pag, frozenset({"nativo"}))


def chunks_de(blocos, **kw):
    params = dict(doc_id="ADI_1", classe="ADI", numero=1, arquivo_pdf="ADI_1_peticao_inicial.pdf",
                  contar_tokens=contar, alvo=20, teto=40)
    params.update(kw)
    return gerar_chunks(blocos, **params)[0]


def test_dividir_em_sentencas_respeita_abreviacoes():
    texto = "Conforme o art. 5º da CF, cabe a ação. Ver fls. 10 dos autos. O Min. Relator decidiu."
    assert dividir_em_sentencas(texto) == [
        "Conforme o art. 5º da CF, cabe a ação.",
        "Ver fls. 10 dos autos.",
        "O Min. Relator decidiu.",
    ]


def test_cabecalho():
    assert cabecalho("ADI", 5613, "I – O OBJETO") == "ADI 5613 | I – O OBJETO"
    assert cabecalho("ADC", 27, "") == "ADC 27"


def test_agrupa_paragrafos_ate_o_alvo():
    blocos = [P("um dois três quatro cinco seis sete oito."), P("nove dez onze doze treze catorze quinze."),
              P("alfa beta gama delta épsilon zeta eta teta iota capa.")]
    chunks = chunks_de(blocos)
    assert [c["texto"] for c in chunks] == [
        "um dois três quatro cinco seis sete oito.\n\nnove dez onze doze treze catorze quinze.",
        "alfa beta gama delta épsilon zeta eta teta iota capa.",
    ]
    assert [c["chunk_id"] for c in chunks] == ["ADI_1_0000", "ADI_1_0001"]


def test_titulo_abre_chunk_e_define_secao():
    blocos = [P("Introdução curta da petição aqui."), T("I. DOS FATOS"), P("Os fatos são estes."),
              T("II. DO DIREITO"), P("O direito é este.")]
    chunks = chunks_de(blocos)
    assert [c["secao"] for c in chunks] == ["", "I. DOS FATOS", "II. DO DIREITO"]
    assert chunks[1]["texto"] == "I. DOS FATOS\n\nOs fatos são estes."
    assert chunks[1]["texto_embedding"] == "ADI 1 | I. DOS FATOS\nI. DOS FATOS\n\nOs fatos são estes."


def test_titulos_consecutivos_ficam_no_mesmo_chunk():
    chunks = chunks_de([T("I. DO MÉRITO"), T("I.1 DOS FATOS"), P("Os fatos são estes aqui.")])
    assert len(chunks) == 1
    assert chunks[0]["secao"] == "I.1 DOS FATOS"


def test_paragrafo_gigante_e_quebrado_respeitando_o_teto():
    sentencas = [" ".join(f"p{i}_{j}" for j in range(9)) + "." for i in range(12)]
    chunks = chunks_de([P(" ".join(sentencas), 3, 5)])
    assert len(chunks) > 1
    assert all(c["n_tokens"] <= 40 for c in chunks)
    assert " ".join(c["texto"] for c in chunks) == " ".join(sentencas)
    assert all((c["pagina_inicio"], c["pagina_fim"]) == (3, 5) for c in chunks)


def test_paginas_e_metodo_misto():
    chunks = chunks_de([P("um dois três quatro cinco.", 2, 2, "nativo"), P("seis sete oito nove dez.", 2, 3, "ocr")])
    assert len(chunks) == 1
    c = chunks[0]
    assert (c["pagina_inicio"], c["pagina_fim"], c["metodo_extracao"]) == (2, 3, "misto")


def test_continua_numeracao_e_secao_entre_partes():
    chunks, secao = gerar_chunks(
        [P("Continuação do argumento na parte dois.")],
        doc_id="ADI_1", classe="ADI", numero=1, arquivo_pdf="ADI_1_peticao_inicial_parte02.pdf",
        contar_tokens=contar, indice_inicial=7, secao_inicial="III. DO MÉRITO",
    )
    assert chunks[0]["chunk_id"] == "ADI_1_0007"
    assert chunks[0]["secao"] == "III. DO MÉRITO"
    assert secao == "III. DO MÉRITO"


def test_descarta_resto_sem_conteudo():
    assert chunks_de([P("1 2 3 - 4")]) == []


def test_muitos_titulos_seguidos_nao_estouram_o_teto():
    titulos = [T(f"{i}. ITEM EM MAIÚSCULAS DE UM ÍNDICE DIGITALIZADO") for i in range(30)]
    chunks = chunks_de(titulos)
    assert len(chunks) > 1
    assert all(c["n_tokens"] <= 40 for c in chunks)
