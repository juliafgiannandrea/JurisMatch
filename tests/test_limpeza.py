from jurismatch.limpeza import Linha, eh_ruido, limpar_paginas, linhas_repetidas, normalizar
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
