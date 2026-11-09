"""Etapa 02 (limpeza): texto do OCR -> texto limpo + relatório por arquivo.

Uso: python scripts/02_clean.py   (ou python -m jurismatch.pipeline_limpeza)

Lê data/02_processed/ocr/*.txt, remove ruído (carimbos, números de página, cabeçalhos e
rodapés repetidos, sumários) e grava data/02_processed/clean/*.txt com o mesmo nome e os
mesmos marcadores [[pagina N | metodo]]. O relatório fica em clean/relatorio_limpeza.csv.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import pandas as pd

from jurismatch import config
from jurismatch.limpeza import RE_RUIDO, gravar_linhas, limpar_paginas, normalizar
from jurismatch.paginas import Pagina, agrupar_por_peticao, ler_paginas


def paginas_so_com_carimbo(paginas: list[Pagina]) -> int:
    """Páginas 'nativas' cujo único texto é carimbo de assinatura (faltou OCR na etapa 01)."""
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


def limpar_corpus(dir_ocr: Path, dir_clean: Path) -> pd.DataFrame:
    """Grava um .txt limpo para cada .txt do OCR e devolve o relatório por arquivo."""
    dir_clean.mkdir(parents=True, exist_ok=True)
    relatorio: list[dict] = []
    for doc_id, arquivos in agrupar_por_peticao(dir_ocr).items():
        for arquivo in arquivos:
            paginas = ler_paginas(arquivo.caminho.read_text(encoding="utf-8"))
            linhas = limpar_paginas(paginas)
            (dir_clean / arquivo.caminho.name).write_text(gravar_linhas(linhas), encoding="utf-8")
            metodos = Counter(p.metodo for p in paginas)
            relatorio.append(
                {
                    "arquivo": arquivo.caminho.name,
                    "doc_id": doc_id,
                    "classe": arquivo.classe,
                    "numero": arquivo.numero,
                    "parte": arquivo.parte,
                    "arquivo_pdf": arquivo.arquivo_pdf,
                    "paginas": len(paginas),
                    "paginas_nativas": metodos["nativo"],
                    "paginas_ocr": metodos["ocr"],
                    "paginas_vazias": metodos["vazia"],
                    "paginas_so_com_carimbo": paginas_so_com_carimbo(paginas),
                    "linhas_brutas": sum(1 for p in paginas for l in p.texto.split("\n") if l.strip()),
                    "linhas_mantidas": sum(1 for l in linhas if l.texto),
                }
            )
    return pd.DataFrame(relatorio)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir-ocr", type=Path, default=config.DIR_OCR)
    parser.add_argument("--dir-clean", type=Path, default=config.DIR_CLEAN)
    args = parser.parse_args()

    relatorio = limpar_corpus(args.dir_ocr, args.dir_clean)
    arq_relatorio = args.dir_clean / config.ARQ_RELATORIO_LIMPEZA.name
    relatorio.to_csv(arq_relatorio, index=False, sep=";", encoding="utf-8-sig")
    print(f"{len(relatorio)} arquivos limpos -> {args.dir_clean}")
    print(f"Linhas mantidas: {relatorio['linhas_mantidas'].sum()} de {relatorio['linhas_brutas'].sum()}")
    suspeitos = relatorio[relatorio["paginas_so_com_carimbo"] > 0]
    if not suspeitos.empty:
        print("\nATENÇÃO: arquivos que precisam voltar para o OCR (scripts/01_ocr.py --forcar):")
        print(suspeitos[["arquivo", "paginas", "paginas_so_com_carimbo"]].to_string(index=False))


if __name__ == "__main__":
    main()
