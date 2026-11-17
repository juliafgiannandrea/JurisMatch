"""Metadados de classificação por petição: a norma impugnada é medida provisória? há pedido de liminar?

São perguntas sobre a petição inteira, que a busca por semelhança não responde bem: ela acha os trechos
mais parecidos com a consulta, mas não verifica um critério em cada petição. Aqui o critério é avaliado
uma vez por petição e vira coluna dos chunks, usada como filtro na busca.

Impugnação de MP, validada contra a coluna MP da planilha de casos de teste (430 ADIs, 63 contra MP):
precisão 0,88 e recall 0,94.
  1. Se a planilha base do STF traz a coluna Legislação da petição: é MP quando a Legislação cita uma
     medida provisória E o texto da petição menciona alguma ao menos uma vez. A segunda condição corta
     processos cuja Legislação lista uma MP só como norma relacionada.
  2. Senão: ao menos MIN_MENCOES_MP menções a "Medida Provisória nº ..." nas PAGINAS_OBJETO primeiras
     páginas, onde ficam a qualificação do objeto da ação e o pedido.

Pedido de liminar: alguma menção a medida cautelar, liminar ou tutela de urgência na petição. Aparece
em ~97% das petições, então como filtro separa pouco; serve sobretudo para achar as que não pedem.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from jurismatch.paginas import agrupar_por_peticao, ler_paginas

PAGINAS_OBJETO = 10
MIN_MENCOES_MP = 3

RE_MENCAO_MP = re.compile(
    r"medida\s+provis[óo]ria\s*(?:n[º°o.]*\s*)?\d|\bMPV?\s*n?[º°o.]*\s*\d{3,4}", re.IGNORECASE
)
RE_LEGISLACAO_MP = re.compile(r"medida\s+provis|\bMPV\b", re.IGNORECASE)
RE_LIMINAR = re.compile(r"medida\s+cautelar|liminar|tutela\s+(?:de\s+urg[êe]ncia|provis[óo]ria)", re.IGNORECASE)

COLUNAS = ["impugna_mp", "pedido_liminar"]  # vão para os chunks e viram filtros da busca


def carregar_legislacao(planilha: Path) -> dict[str, str]:
    """doc_id (ex.: ADI_6115) -> coluna Legislação da planilha base do STF. Sem planilha: vazio."""
    try:
        base = pd.read_excel(planilha, usecols=["Processo", "Legislação"])
    except (OSError, ValueError):
        return {}
    base = base.dropna()
    return dict(zip(base["Processo"].str.strip().str.replace(" ", "_"), base["Legislação"].astype(str)))


def classificar_peticao(paginas: list[str], legislacao: str | None = None) -> dict:
    """Classifica uma petição a partir do texto de cada página (em ordem) e da Legislação, se houver."""
    mencoes_objeto = sum(len(RE_MENCAO_MP.findall(p)) for p in paginas[:PAGINAS_OBJETO])
    if legislacao:
        impugna_mp = bool(RE_LEGISLACAO_MP.search(legislacao)) and mencoes_objeto >= 1
        fonte = "legislacao"
    else:
        impugna_mp = mencoes_objeto >= MIN_MENCOES_MP
        fonte = "texto"
    return {
        "impugna_mp": impugna_mp,
        "fonte_mp": fonte,
        "mencoes_mp": mencoes_objeto,
        "pedido_liminar": any(RE_LIMINAR.search(p) for p in paginas),
    }


def classificar_corpus(dir_txt: Path, legislacao: dict[str, str] | None = None) -> pd.DataFrame:
    """Uma linha por petição (doc_id) com as colunas de classificação."""
    legislacao = legislacao or {}
    linhas = []
    for doc_id, arquivos in agrupar_por_peticao(dir_txt).items():
        paginas = [p.texto for a in arquivos for p in ler_paginas(a.caminho.read_text(encoding="utf-8"))]
        linhas.append({"doc_id": doc_id, **classificar_peticao(paginas, legislacao.get(doc_id))})
    return pd.DataFrame(linhas, columns=["doc_id", "impugna_mp", "fonte_mp", "mencoes_mp", "pedido_liminar"])
