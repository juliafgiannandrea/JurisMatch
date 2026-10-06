"""Leitura dos .txt da etapa 2: identifica a petição e separa o texto por página."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

RE_MARCADOR = re.compile(r"^\[\[pagina (\d+) \| ([a-z_]+)\]\][ \t]*$", re.MULTILINE)
RE_NOME = re.compile(r"^(ADI|ADC)_(\d+)_peticao_inicial(?:_parte(\d+))?\.txt$")


@dataclass(frozen=True)
class Pagina:
    numero: int
    metodo: str  # "nativo", "ocr" ou "vazia"
    texto: str


@dataclass(frozen=True)
class ArquivoPeticao:
    caminho: Path
    classe: str  # "ADI" ou "ADC"
    numero: int
    parte: int  # 1 quando a petição não foi dividida em partes

    @property
    def doc_id(self) -> str:
        return f"{self.classe}_{self.numero}"

    @property
    def arquivo_pdf(self) -> str:
        return self.caminho.with_suffix(".pdf").name


def identificar_arquivo(caminho: Path) -> ArquivoPeticao:
    m = RE_NOME.match(caminho.name)
    if m is None:
        raise ValueError(f"Nome de arquivo fora do padrão: {caminho.name}")
    return ArquivoPeticao(
        caminho=caminho,
        classe=m.group(1),
        numero=int(m.group(2)),
        parte=int(m.group(3) or 1),
    )


def ler_paginas(texto: str) -> list[Pagina]:
    """Divide o texto nos marcadores [[pagina N | metodo]]."""
    marcadores = list(RE_MARCADOR.finditer(texto))
    paginas = []
    for i, m in enumerate(marcadores):
        fim = marcadores[i + 1].start() if i + 1 < len(marcadores) else len(texto)
        paginas.append(
            Pagina(numero=int(m.group(1)), metodo=m.group(2), texto=texto[m.end():fim].strip("\n"))
        )
    return paginas


def agrupar_por_peticao(dir_txt: Path) -> dict[str, list[ArquivoPeticao]]:
    """Mapa doc_id -> arquivos da petição, em ordem de parte."""
    grupos: dict[str, list[ArquivoPeticao]] = {}
    for caminho in sorted(dir_txt.glob("*.txt")):
        arquivo = identificar_arquivo(caminho)
        grupos.setdefault(arquivo.doc_id, []).append(arquivo)
    for arquivos in grupos.values():
        arquivos.sort(key=lambda a: a.parte)
    return grupos
