from pathlib import Path

import pytest

from jurismatch.paginas import agrupar_por_peticao, identificar_arquivo, ler_paginas

TEXTO = (
    "[[pagina 1 | nativo]]\n\nPrimeira página.\n\n1\n\n"
    "[[pagina 2 | ocr]]\n\nSegunda página.\n\n"
    "[[pagina 3 | vazia]]\n"
)


def test_ler_paginas_separa_por_marcador():
    paginas = ler_paginas(TEXTO)
    assert [(p.numero, p.metodo) for p in paginas] == [(1, "nativo"), (2, "ocr"), (3, "vazia")]
    assert "Primeira página." in paginas[0].texto
    assert "[[pagina" not in paginas[0].texto
    assert paginas[2].texto == ""


def test_identificar_arquivo_simples():
    a = identificar_arquivo(Path("ADC_100_peticao_inicial.txt"))
    assert (a.classe, a.numero, a.parte, a.doc_id) == ("ADC", 100, 1, "ADC_100")
    assert a.arquivo_pdf == "ADC_100_peticao_inicial.pdf"


def test_identificar_arquivo_com_parte():
    a = identificar_arquivo(Path("ADI_3494_peticao_inicial_parte03.txt"))
    assert (a.doc_id, a.parte) == ("ADI_3494", 3)
    assert a.arquivo_pdf == "ADI_3494_peticao_inicial_parte03.pdf"


def test_identificar_arquivo_fora_do_padrao():
    with pytest.raises(ValueError):
        identificar_arquivo(Path("log_extracao.txt"))


def test_agrupar_por_peticao_junta_partes(tmp_path):
    for nome in [
        "ADI_2945_peticao_inicial_parte02.txt",
        "ADI_2945_peticao_inicial_parte01.txt",
        "ADC_27_peticao_inicial.txt",
    ]:
        (tmp_path / nome).write_text("[[pagina 1 | nativo]]\n\nx\n", encoding="utf-8")
    (tmp_path / "log_extracao.csv").write_text("a;b\n", encoding="utf-8")
    grupos = agrupar_por_peticao(tmp_path)
    assert sorted(grupos) == ["ADC_27", "ADI_2945"]
    assert [a.parte for a in grupos["ADI_2945"]] == [1, 2]
