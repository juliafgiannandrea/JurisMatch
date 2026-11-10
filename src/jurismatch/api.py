"""API FastAPI do JurisMatch: /api/* + PWA estático (app/web) na raiz.

Uso: python -m jurismatch.api [--host 127.0.0.1] [--port 8000]
"""
from __future__ import annotations

import argparse
import math
import re
import threading
import time
from pathlib import Path
from typing import Callable, Literal

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from jurismatch import config
from jurismatch.busca import MODOS, Buscador

CLASSES = ("ADI", "ADC", "ADO", "ADPF")
NOME_PDF = re.compile(r"^[A-Za-z0-9_.-]+\.pdf$")
MSG_SEM_INDICE = "Índice não encontrado. Rode python -m jurismatch.indexar."


class Consulta(BaseModel):
    consulta: str = Field(min_length=1, max_length=500)
    k: int = Field(default=5, ge=1, le=20)
    modo: Literal["hibrido", "denso", "lexical"] = "hibrido"
    classe: Literal["ADI", "ADC", "ADO", "ADPF"] | None = None
    rerank: bool = True
    limiar: float = Field(default=config.LIMIAR_RERANK, ge=0.0, le=1.0)

    @field_validator("consulta", mode="before")
    @classmethod
    def _aparar(cls, v):
        return v.strip() if isinstance(v, str) else v


class _Estaticos(StaticFiles):
    """StaticFiles que impede o navegador de guardar o service worker em cache HTTP."""

    async def get_response(self, path, scope):
        resposta = await super().get_response(path, scope)
        if path == "sw.js":
            resposta.headers["Cache-Control"] = "no-cache"
        return resposta


def _json_seguro(valor):
    """numpy/NaN -> tipos JSON (NaN vira None)."""
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return None
    if hasattr(valor, "item"):
        return _json_seguro(valor.item())
    return valor


def carregar_incidentes(arquivo: Path) -> dict[str, str]:
    """doc_id (ex.: ADC_27) -> incidente numérico do STF, lido de log_download.csv. Ausente = vazio."""
    try:
        tabela = pd.read_csv(arquivo, sep=";", encoding="utf-8-sig", dtype=str)
        pares = zip(tabela["processo"], tabela["incidente"])
    except (OSError, KeyError, ValueError, pd.errors.ParserError):
        return {}
    return {
        processo.strip().replace(" ", "_"): incidente.strip()
        for processo, incidente in pares
        if isinstance(processo, str) and isinstance(incidente, str) and incidente.strip().isdigit()
    }


def criar_app(
    fabrica_buscador: Callable[[], Buscador] | None = None,
    dir_indice: Path = config.DIR_INDICE,
    dir_pdf: Path = config.DIR_PDF,
    dir_web: Path = config.DIR_WEB,
    arq_incidentes: Path = config.ARQ_INCIDENTES,
) -> FastAPI:
    if fabrica_buscador is None:
        fabrica_buscador = lambda: Buscador(dir_indice)  # noqa: E731

    app = FastAPI(title="JurisMatch", docs_url=None, redoc_url=None)
    estado: dict = {"buscador": None, "contagens": None}
    trava_carga = threading.Lock()
    trava_busca = threading.Lock()
    dir_pdf_real = Path(dir_pdf).resolve()
    incidentes = carregar_incidentes(Path(arq_incidentes))

    def indice_pronto() -> bool:
        return (Path(dir_indice) / "chunks.parquet").exists() and (Path(dir_indice) / "faiss.index").exists()

    def contagens() -> tuple[int, int]:
        if estado["contagens"] is None:
            chunks = pd.read_parquet(Path(dir_indice) / "chunks.parquet", columns=["doc_id"])
            estado["contagens"] = (int(chunks["doc_id"].nunique()), len(chunks))
        return estado["contagens"]

    def buscador() -> Buscador:
        with trava_carga:
            if estado["buscador"] is None:
                estado["buscador"] = fabrica_buscador()
            return estado["buscador"]

    def pdf_existe(nome: str) -> bool:
        if not isinstance(nome, str) or not NOME_PDF.match(nome):
            return False
        caminho = (dir_pdf_real / nome).resolve()
        return caminho.parent == dir_pdf_real and caminho.is_file()

    @app.get("/api/status")
    def status():
        pronto = indice_pronto()
        peticoes, trechos = contagens() if pronto else (None, None)
        return {
            "indice_pronto": pronto,
            "buscador_carregado": estado["buscador"] is not None,
            "peticoes": peticoes,
            "trechos": trechos,
            "modelo_embedding": config.MODELO_EMBEDDING,
            "modelo_reranker": config.MODELO_RERANKER,
            "limiar_padrao": config.LIMIAR_RERANK,
            "modos": list(MODOS),
            "classes": list(CLASSES),
        }

    @app.post("/api/buscar")
    def buscar(corpo: Consulta):
        if not indice_pronto():
            raise HTTPException(status_code=503, detail=MSG_SEM_INDICE)
        inicio = time.perf_counter()
        b = buscador()
        with trava_busca:
            brutos = b.buscar(
                corpo.consulta, k=corpo.k, modo=corpo.modo, classe=corpo.classe,
                rerank=corpo.rerank, limiar=corpo.limiar,
            )
        resultados = []
        for r in brutos:
            item = {k: _json_seguro(v) for k, v in r.items() if k != "link_pdf"}
            disponivel = pdf_existe(item["arquivo_pdf"])
            item["pdf_disponivel"] = disponivel
            item["url_pdf"] = f"/api/pdf/{item['arquivo_pdf']}#page={item['pagina']}" if disponivel else None
            incidente = incidentes.get(item["doc_id"])
            item["url_stf"] = config.URL_PROCESSO_STF.format(incidente=incidente) if incidente else None
            resultados.append(item)
        return {
            "consulta": corpo.consulta,
            "rerank": corpo.rerank,
            "limiar": corpo.limiar,
            "tempo_ms": int((time.perf_counter() - inicio) * 1000),
            "resultados": resultados,
        }

    @app.get("/api/pdf/{arquivo}")
    def pdf(arquivo: str):
        if not pdf_existe(arquivo):
            raise HTTPException(status_code=404, detail="PDF não encontrado.")
        caminho = (dir_pdf_real / arquivo).resolve()
        return FileResponse(
            caminho,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{arquivo}"'},
        )

    # Por último: as rotas /api têm precedência. check_dir=False deixa a API subir sem app/web.
    app.mount("/", _Estaticos(directory=dir_web, html=True, check_dir=False), name="web")
    return app


app = criar_app()


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
