from jurismatch.limpeza import (
    Linha,
    eh_destaque,
    eh_ruido,
    eh_titulo,
    limpar_paginas,
    linhas_repetidas,
    montar_blocos,
    normalizar,
)
from jurismatch.paginas import Pagina


def L(texto, pagina=1, metodo="nativo"):
    return Linha(texto, pagina, metodo)


def test_normalizar_troca_nbsp_ligadura_e_espacos():
    assert normalizar("  art. 5º   da\tCons­tituição eﬁcaz ") == "art. 5º da Constituição eficaz"


def test_normalizar_preserva_acentos_compostos():
    assert normalizar("ação") == "ação"


def test_eh_ruido():
    assert eh_ruido("12")
    assert eh_ruido("Página 3 de 20")
    assert eh_ruido("Signature Not Verified")
    assert eh_ruido("Assinado por FULANO DE TAL:123 em 19/03/2010 12:49:37")
    assert eh_ruido("_______________________________")
    assert eh_ruido("(...)")
    assert not eh_ruido("9868/99, propor")
    assert not eh_ruido("AÇÃO DIRETA DE INCONSTITUCIONALIDADE")


def test_linhas_repetidas_detecta_cabecalho_com_numero_variavel():
    corpo = ["alfa", "beta", "gama", "delta", "épsilon", "zeta"]
    paginas = [["Escritório X Advogados", f"texto sobre {c}", f"Rua Y, 10 - fl. {i}"] for i, c in enumerate(corpo)]
    assert linhas_repetidas(paginas) == {"escritório x advogados", "rua y, # - fl. #"}


def test_linhas_repetidas_ignora_documento_curto():
    assert linhas_repetidas([["Cabeçalho"], ["Cabeçalho"], ["Cabeçalho"]]) == set()


def test_limpar_paginas_remove_sumario_ruido_e_cabecalho():
    temas = ["alfa", "beta", "gama", "delta", "épsilon"]
    paginas = [
        Pagina(n, "nativo", f"Timbre do Escritório\n\nParágrafo sobre {tema}.\n\n{n}")
        for n, tema in enumerate(temas, start=1)
    ]
    paginas.insert(
        1,
        Pagina(99, "nativo", "SUMÁRIO\nI. FATOS ........ 3\nII. DIREITO ........ 5\nIII. PEDIDO ........ 9"),
    )
    paginas.append(Pagina(7, "vazia", ""))
    textos = [l.texto for l in limpar_paginas(paginas) if l.texto]
    assert textos == [f"Parágrafo sobre {tema}." for tema in temas]


def test_eh_titulo():
    assert eh_titulo("I. NECESSÁRIA DISTRIBUIÇÃO POR PREVENÇÃO", True)
    assert eh_titulo("I- DA DISTRIBUIÇÃO POR DEPENDÊNCIA ÀS ADIs 7.827 e 7.839", False)
    assert eh_titulo("I –O OBJETO DESTA AÇÃO DIRETA DE INCONSTITUCIONALIDADE", True)
    assert eh_titulo("II – Da legitimidade ativa", True)
    assert eh_titulo("3. DO PEDIDO CAUTELAR", True)
    assert eh_titulo("II.2 ADVOCACIA PRIVADA E PÚBLICA", True)
    assert not eh_titulo("AÇÃO DIRETA DE INCONSTITUCIONALIDADE", True)  # sem numeração: é destaque
    assert not eh_titulo("INCONSTITUCIONALIDADE DA LEI IMPUGNADA", True)
    assert not eh_titulo("V.Exa., muito respeitosamente, ajuizar a presente", True)
    assert not eh_titulo("I, “a” e no art. 103, inciso IX, da Constituição Federal,", True)
    assert not eh_titulo("L. A. MACHADO, PROFESSOR TITULAR DA FACULDADE DE DIREITO", True)
    assert not eh_titulo("94-27-95 1:15: 16 RECIBIDO DE:~553412951 P.04", True)
    assert not eh_titulo("9.504/97. PROIBIÇÃO IMPOSTA AOS CANDIDATOS", True)
    assert not eh_titulo("5. Ademais, os adeptos desse entendimento afirmam haver", True)
    assert not eh_titulo(
        "II - Quando a produção ocorrer na plataforma continental, no mar territorial ou na", True
    )


def test_eh_destaque():
    assert eh_destaque("AÇÃO DIRETA DE INCONSTITUCIONALIDADE")
    assert not eh_destaque("em face do art. 1º da Lei 8540/92")


def test_montar_blocos_destaque_vira_paragrafo_proprio():
    linhas = [
        L("EXCELENTÍSSIMO SENHOR MINISTRO PRESIDENTE DO"),
        L("SUPREMO TRIBUNAL FEDERAL"),
        L(""),
        L("A ASSOCIAÇÃO X vem propor a presente"),
        L(""),
        L("AÇÃO DIRETA DE INCONSTITUCIONALIDADE"),
        L(""),
        L("em face da Lei Y."),
    ]
    blocos = montar_blocos(linhas)
    assert [(b.tipo, b.texto) for b in blocos] == [
        ("paragrafo", "EXCELENTÍSSIMO SENHOR MINISTRO PRESIDENTE DO SUPREMO TRIBUNAL FEDERAL"),
        ("paragrafo", "A ASSOCIAÇÃO X vem propor a presente AÇÃO DIRETA DE INCONSTITUCIONALIDADE em face da Lei Y."),
    ]


def test_montar_blocos_rejunta_linhas_com_espacamento_duplo():
    linhas = [
        L("ABRAFRIGO, pessoa jurídica de direito privado, com"),
        L(""),
        L("sede em Curitiba, CEP 80.540-"),
        L(""),
        L("290, vem propor a presente ação."),
        L(""),
        L("Outro parágrafo começa aqui."),
    ]
    blocos = montar_blocos(linhas)
    assert [b.texto for b in blocos] == [
        "ABRAFRIGO, pessoa jurídica de direito privado, com sede em Curitiba, CEP 80.540-290, "
        "vem propor a presente ação.",
        "Outro parágrafo começa aqui.",
    ]


def test_montar_blocos_hifenizacao():
    blocos = montar_blocos([L("norma incons-"), L("titucional que declara-"), L("se nula.")])
    assert blocos[0].texto == "norma inconstitucional que declara-se nula."


def test_montar_blocos_paragrafo_atravessa_pagina():
    linhas = [
        L("5. O parágrafo começa na página dois e", 2, "nativo"),
        L("", 2, "nativo"),
        L("termina na página três.", 3, "ocr"),
        L("6. Novo parágrafo numerado.", 3, "ocr"),
    ]
    blocos = montar_blocos(linhas)
    assert len(blocos) == 2
    assert (blocos[0].pagina_inicio, blocos[0].pagina_fim) == (2, 3)
    assert blocos[0].metodos == frozenset({"nativo", "ocr"})
    assert blocos[1].texto == "6. Novo parágrafo numerado."


def test_montar_blocos_titulo_em_duas_linhas():
    linhas = [
        L("Fim do parágrafo anterior."),
        L(""),
        L("II. REQUISITOS FORMAIS: OBJETO DESTA ADC E"),
        L("PERTINÊNCIA TEMÁTICA"),
        L(""),
        L("Texto da seção."),
    ]
    blocos = montar_blocos(linhas)
    assert [(b.tipo, b.texto) for b in blocos] == [
        ("paragrafo", "Fim do parágrafo anterior."),
        ("titulo", "II. REQUISITOS FORMAIS: OBJETO DESTA ADC E PERTINÊNCIA TEMÁTICA"),
        ("paragrafo", "Texto da seção."),
    ]


def test_montar_blocos_inciso_de_lei_nao_vira_titulo():
    linhas = [
        L("Art. 3º Compete ao Conselho:"),
        L("I - Convocar reunião extraordinária"),
        L("II - Aprovar o regimento interno."),
    ]
    assert all(b.tipo == "paragrafo" for b in montar_blocos(linhas))
