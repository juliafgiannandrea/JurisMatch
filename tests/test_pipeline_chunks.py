import pandas as pd

from jurismatch.paginas import Pagina
from jurismatch.pipeline_chunks import montar_documentos, processar_corpus
from jurismatch.pipeline_limpeza import limpar_corpus, paginas_so_com_carimbo

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


def _corpus(tmp_path):
    ocr, clean = tmp_path / "ocr", tmp_path / "clean"
    ocr.mkdir()
    escrever(ocr, "ADI_10_peticao_inicial_parte01.txt", [
        (1, "nativo", "I. DOS FATOS\n\nA requerente narra os fatos que motivam a presente ação direta."),
    ])
    escrever(ocr, "ADI_10_peticao_inicial_parte02.txt", [
        (1, "ocr", "A narrativa continua na segunda parte do arquivo digitalizado."),
    ])
    escrever(ocr, "ADC_20_peticao_inicial.txt", [(1, "nativo", CARIMBO), (2, "nativo", CARIMBO)])
    (ocr / "log_extracao.csv").write_text("arquivo;paginas\n", encoding="utf-8")
    relatorio = limpar_corpus(ocr, clean)
    return clean, relatorio


def test_limpar_corpus_grava_um_txt_limpo_por_arquivo(tmp_path):
    clean, relatorio = _corpus(tmp_path)
    assert sorted(p.name for p in clean.glob("*.txt")) == [
        "ADC_20_peticao_inicial.txt",
        "ADI_10_peticao_inicial_parte01.txt",
        "ADI_10_peticao_inicial_parte02.txt",
    ]
    assert "Documento assinado" not in (clean / "ADC_20_peticao_inicial.txt").read_text(encoding="utf-8")
    adc = relatorio.set_index("arquivo").loc["ADC_20_peticao_inicial.txt"]
    assert adc["paginas_so_com_carimbo"] == 2 and adc["paginas_nativas"] == 2


def test_processar_corpus_junta_partes(tmp_path):
    clean, _ = _corpus(tmp_path)
    chunks, por_arquivo = processar_corpus(clean, contar)

    assert chunks["chunk_id"].tolist() == ["ADI_10_0000", "ADI_10_0001"]
    assert chunks["arquivo_pdf"].tolist() == [
        "ADI_10_peticao_inicial_parte01.pdf",
        "ADI_10_peticao_inicial_parte02.pdf",
    ]
    assert chunks["secao"].tolist() == ["I. DOS FATOS", "I. DOS FATOS"]  # a seção atravessa as partes
    assert chunks["metodo_extracao"].tolist() == ["nativo", "ocr"]
    assert por_arquivo.set_index("arquivo").loc["ADC_20_peticao_inicial.txt", "chunks"] == 0


def test_montar_documentos_uma_linha_por_peticao(tmp_path):
    clean, relatorio = _corpus(tmp_path)
    chunks, por_arquivo = processar_corpus(clean, contar)
    docs = montar_documentos(relatorio.merge(por_arquivo[["arquivo", "chunks"]], on="arquivo"), chunks)
    docs = docs.set_index("doc_id")

    assert list(docs.index) == ["ADC_20", "ADI_10"]
    adi = docs.loc["ADI_10"]
    assert adi["partes"] == 2 and adi["chunks"] == 2 and adi["metodo_extracao"] == "misto"
    assert adi["arquivos_pdf"] == "ADI_10_peticao_inicial_parte01.pdf|ADI_10_peticao_inicial_parte02.pdf"
    assert not adi["reprocessar_ocr"]
    assert docs.loc["ADC_20", "reprocessar_ocr"] and docs.loc["ADC_20", "chunks"] == 0


def test_montar_documentos_sem_chunks():
    relatorio = pd.DataFrame([{
        "arquivo": "ADC_1_peticao_inicial.txt", "doc_id": "ADC_1", "classe": "ADC", "numero": 1,
        "arquivo_pdf": "ADC_1_peticao_inicial.pdf", "paginas": 1, "paginas_nativas": 1, "paginas_ocr": 0,
        "paginas_vazias": 0, "paginas_so_com_carimbo": 1,
    }])
    docs = montar_documentos(relatorio, pd.DataFrame())
    assert docs.loc[0, "chunks"] == 0 and docs.loc[0, "reprocessar_ocr"]
