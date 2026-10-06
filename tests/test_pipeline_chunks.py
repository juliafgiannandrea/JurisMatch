from jurismatch.paginas import Pagina
from jurismatch.pipeline_chunks import paginas_so_com_carimbo, processar_corpus

CARIMBO = (
    "Documento assinado digitalmente conforme MP n° 2.200-2/2001 de 24/08/2001, que institui a "
    "Infra-estrutura de Chaves Públicas Brasileira - ICP-Brasil. O\n"
    "documento pode ser acessado no endereço eletrônico "
    "http://www.stf.jus.br/portal/autenticacao/autenticarDocumento.asp sob o número 400937"
)


def contar(texto):
    return len(texto.split())


def escrever(pasta, nome, paginas):
    corpo = "".join(f"[[pagina {n} | {metodo}]]\n\n{texto}\n\n" for n, metodo, texto in paginas)
    (pasta / nome).write_text(corpo, encoding="utf-8")


def test_paginas_so_com_carimbo():
    paginas = [
        Pagina(1, "nativo", CARIMBO),
        Pagina(2, "nativo", CARIMBO + "\n" + "Texto real da petição. " * 10),
        Pagina(3, "ocr", "x"),
    ]
    assert paginas_so_com_carimbo(paginas) == 1


def test_processar_corpus_junta_partes_e_gera_relatorio(tmp_path):
    escrever(tmp_path, "ADI_10_peticao_inicial_parte01.txt", [
        (1, "nativo", "I. DOS FATOS\n\nA requerente narra os fatos que motivam a presente ação direta."),
    ])
    escrever(tmp_path, "ADI_10_peticao_inicial_parte02.txt", [
        (1, "ocr", "A narrativa continua na segunda parte do arquivo digitalizado."),
    ])
    escrever(tmp_path, "ADC_20_peticao_inicial.txt", [(1, "nativo", CARIMBO), (2, "nativo", CARIMBO)])
    (tmp_path / "log_extracao.csv").write_text("arquivo;paginas\n", encoding="utf-8")

    chunks, relatorio = processar_corpus(tmp_path, contar)

    assert chunks["chunk_id"].tolist() == ["ADI_10_0000", "ADI_10_0001"]
    assert chunks["arquivo_pdf"].tolist() == [
        "ADI_10_peticao_inicial_parte01.pdf",
        "ADI_10_peticao_inicial_parte02.pdf",
    ]
    assert chunks["secao"].tolist() == ["I. DOS FATOS", "I. DOS FATOS"]  # a seção atravessa as partes
    assert chunks["metodo_extracao"].tolist() == ["nativo", "ocr"]
    adc = relatorio.set_index("arquivo").loc["ADC_20_peticao_inicial.txt"]
    assert adc["paginas_so_com_carimbo"] == 2 and adc["chunks"] == 0
