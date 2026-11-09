"""Etapa 03 (chunking): texto limpo -> chunks com metadados + relatório + metadata/documentos.csv.

Uso: python scripts/03_chunk.py   (ou python -m jurismatch.pipeline_chunks)

Lê data/02_processed/clean/*.txt (gerados por scripts/02_clean.py) e grava
data/03_chunks/chunks.parquet, data/03_chunks/relatorio_chunks.csv e metadata/documentos.csv.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from jurismatch import config
from jurismatch.chunking import ContarTokens, gerar_chunks
from jurismatch.limpeza import ler_linhas, montar_blocos
from jurismatch.paginas import agrupar_por_peticao


def contador_do_modelo(nome_modelo: str) -> ContarTokens:
    """Conta tokens com o tokenizer do próprio modelo de embedding."""
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(nome_modelo)
    return lambda texto: len(tokenizer.encode(texto, add_special_tokens=False))


def processar_corpus(dir_clean: Path, contar_tokens: ContarTokens) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devolve (chunks, nº de chunks por arquivo)."""
    chunks: list[dict] = []
    por_arquivo: list[dict] = []
    for doc_id, arquivos in agrupar_por_peticao(dir_clean).items():
        secao = ""
        inicio_doc = len(chunks)
        for arquivo in arquivos:
            linhas = ler_linhas(arquivo.caminho.read_text(encoding="utf-8"))
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
            por_arquivo.append({"arquivo": arquivo.caminho.name, "doc_id": doc_id, "chunks": len(novos)})
    return pd.DataFrame(chunks), pd.DataFrame(por_arquivo)


def _metodo_predominante(linha: pd.Series) -> str:
    if linha["paginas_ocr"] and linha["paginas_nativas"]:
        return "misto"
    return "ocr" if linha["paginas_ocr"] else "nativo"


def montar_documentos(relatorio: pd.DataFrame, chunks: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por petição: partes, páginas por método de extração, chunks e alerta de OCR."""
    docs = relatorio.groupby("doc_id", sort=True).agg(
        classe=("classe", "first"),
        numero=("numero", "first"),
        partes=("arquivo", "size"),
        arquivos_pdf=("arquivo_pdf", "|".join),
        paginas=("paginas", "sum"),
        paginas_nativas=("paginas_nativas", "sum"),
        paginas_ocr=("paginas_ocr", "sum"),
        paginas_vazias=("paginas_vazias", "sum"),
        paginas_so_com_carimbo=("paginas_so_com_carimbo", "sum"),
    )
    docs["metodo_extracao"] = docs.apply(_metodo_predominante, axis=1)
    if chunks.empty:
        docs["chunks"], docs["tokens"] = 0, 0
    else:
        agregados = chunks.groupby("doc_id").agg(chunks=("chunk_id", "size"), tokens=("n_tokens", "sum"))
        docs = docs.join(agregados).fillna({"chunks": 0, "tokens": 0})
    docs[["chunks", "tokens"]] = docs[["chunks", "tokens"]].astype(int)
    docs["reprocessar_ocr"] = (docs["paginas_so_com_carimbo"] > 0) | (docs["chunks"] == 0)
    return docs.reset_index()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir-clean", type=Path, default=config.DIR_CLEAN)
    parser.add_argument("--saida", type=Path, default=config.ARQ_CHUNKS)
    parser.add_argument("--documentos", type=Path, default=config.ARQ_DOCUMENTOS)
    parser.add_argument("--modelo", default=config.MODELO_EMBEDDING)
    args = parser.parse_args()

    arq_limpeza = args.dir_clean / config.ARQ_RELATORIO_LIMPEZA.name
    if not arq_limpeza.exists():
        raise SystemExit(f"{arq_limpeza} não existe; rode antes scripts/02_clean.py")

    chunks, por_arquivo = processar_corpus(args.dir_clean, contador_do_modelo(args.modelo))
    limpeza = pd.read_csv(arq_limpeza, sep=";", encoding="utf-8-sig")
    relatorio = limpeza.merge(por_arquivo[["arquivo", "chunks"]], on="arquivo", how="left")
    relatorio["chunks"] = relatorio["chunks"].fillna(0).astype(int)

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    chunks.to_parquet(args.saida, index=False)
    relatorio.to_csv(args.saida.with_name(config.ARQ_RELATORIO_CHUNKS.name), index=False, sep=";", encoding="utf-8-sig")
    documentos = montar_documentos(relatorio, chunks)
    args.documentos.parent.mkdir(parents=True, exist_ok=True)
    documentos.to_csv(args.documentos, index=False, sep=";", encoding="utf-8-sig")

    print(f"{len(chunks)} chunks de {chunks['doc_id'].nunique()} petições -> {args.saida}")
    print(f"{len(documentos)} petições -> {args.documentos}")
    print(chunks["n_tokens"].describe().round(0).to_string())
    suspeitos = relatorio[(relatorio["paginas_so_com_carimbo"] > 0) | (relatorio["chunks"] == 0)]
    if not suspeitos.empty:
        print("\nATENÇÃO: arquivos que precisam voltar para o OCR (scripts/01_ocr.py --forcar):")
        print(suspeitos[["arquivo", "paginas", "paginas_so_com_carimbo", "chunks"]].to_string(index=False))


if __name__ == "__main__":
    main()
