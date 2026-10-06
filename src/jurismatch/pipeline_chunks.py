"""Etapa 3: .txt da extração -> dados/chunks.parquet + relatório de qualidade.

Uso: python -m jurismatch.pipeline_chunks
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from jurismatch import config
from jurismatch.chunking import ContarTokens, gerar_chunks
from jurismatch.limpeza import RE_RUIDO, limpar_paginas, montar_blocos, normalizar
from jurismatch.paginas import Pagina, agrupar_por_peticao, ler_paginas


def contador_do_modelo(nome_modelo: str) -> ContarTokens:
    """Conta tokens com o tokenizer do próprio modelo de embedding."""
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(nome_modelo)
    return lambda texto: len(tokenizer.encode(texto, add_special_tokens=False))


def paginas_so_com_carimbo(paginas: list[Pagina]) -> int:
    """Páginas 'nativas' cujo único texto é carimbo de assinatura (faltou OCR na etapa 2)."""
    total = 0
    for pagina in paginas:
        if pagina.metodo != "nativo":
            continue
        linhas = [normalizar(l) for l in pagina.texto.split("\n")]
        bruto = sum(len(l) for l in linhas)
        util = sum(len(l) for l in linhas if not any(r.search(l) for r in RE_RUIDO))
        if bruto >= 100 and util < 100:
            total += 1
    return total


def processar_corpus(dir_txt: Path, contar_tokens: ContarTokens) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devolve (chunks, relatório por arquivo)."""
    chunks: list[dict] = []
    relatorio: list[dict] = []
    for doc_id, arquivos in agrupar_por_peticao(dir_txt).items():
        secao = ""
        inicio_doc = len(chunks)
        for arquivo in arquivos:
            paginas = ler_paginas(arquivo.caminho.read_text(encoding="utf-8"))
            linhas = limpar_paginas(paginas)
            novos, secao = gerar_chunks(
                montar_blocos(linhas),
                doc_id=doc_id,
                classe=arquivo.classe,
                numero=arquivo.numero,
                arquivo_pdf=arquivo.arquivo_pdf,
                contar_tokens=contar_tokens,
                indice_inicial=len(chunks) - inicio_doc,
                secao_inicial=secao,
            )
            chunks.extend(novos)
            linhas_brutas = sum(1 for p in paginas for l in p.texto.split("\n") if l.strip())
            relatorio.append(
                {
                    "arquivo": arquivo.caminho.name,
                    "doc_id": doc_id,
                    "paginas": len(paginas),
                    "paginas_so_com_carimbo": paginas_so_com_carimbo(paginas),
                    "linhas_brutas": linhas_brutas,
                    "linhas_mantidas": sum(1 for l in linhas if l.texto),
                    "chunks": len(novos),
                }
            )
    return pd.DataFrame(chunks), pd.DataFrame(relatorio)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir-txt", type=Path, default=config.DIR_TXT)
    parser.add_argument("--saida", type=Path, default=config.ARQ_CHUNKS)
    parser.add_argument("--modelo", default=config.MODELO_EMBEDDING)
    args = parser.parse_args()

    chunks, relatorio = processar_corpus(args.dir_txt, contador_do_modelo(args.modelo))
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    chunks.to_parquet(args.saida, index=False)
    arq_relatorio = args.saida.with_name("relatorio_chunks.csv")
    relatorio.to_csv(arq_relatorio, index=False, sep=";", encoding="utf-8-sig")

    print(f"{len(chunks)} chunks de {chunks['doc_id'].nunique()} petições -> {args.saida}")
    print(chunks["n_tokens"].describe().round(0).to_string())
    suspeitos = relatorio[(relatorio["paginas_so_com_carimbo"] > 0) | (relatorio["chunks"] == 0)]
    if not suspeitos.empty:
        print("\nATENÇÃO: arquivos que precisam voltar para a etapa 2 (OCR):")
        print(suspeitos[["arquivo", "paginas", "paginas_so_com_carimbo", "chunks"]].to_string(index=False))


if __name__ == "__main__":
    main()
