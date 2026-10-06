"""Limpeza conservadora do texto extraído e montagem de parágrafos.

Entrada: páginas de um arquivo (jurismatch.paginas.Pagina).
Saída: blocos (título ou parágrafo), cada um sabendo de que páginas veio.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from jurismatch.paginas import Pagina

MAIUSCULAS = "A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ"

_TROCAS = {
    " ": " ",  # espaço não separável
    "­": "",  # hífen condicional
    "​": "",  # espaço de largura zero
    "﻿": "",  # BOM
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
}
_TABELA_TROCAS = str.maketrans(_TROCAS)

# Linhas que nunca fazem parte do argumento da petição
RE_RUIDO = [
    re.compile(r"^\d{1,4}$"),  # número de página solto
    re.compile(r"^(p[áa]gina|p[áa]g\.?|p\.|fls?\.?)\s*\d+(\s*(de|/)\s*\d+)?$", re.IGNORECASE),
    re.compile(r"^signature not verified$", re.IGNORECASE),
    re.compile(r"^assinado por .+ em \d{2}/\d{2}/\d{4}", re.IGNORECASE),
    re.compile(r"^documento assinado digitalmente", re.IGNORECASE),
    re.compile(r"documento pode ser acessado no endere[çc]o eletr[ôo]nico", re.IGNORECASE),
    re.compile(r"autenticacao/autenticarDocumento", re.IGNORECASE),
    re.compile(r"validacaodocumento", re.IGNORECASE),
]

RE_PONTILHADO_SUMARIO = re.compile(r"\.{5,}\s*\d+\s*$")
# Título numerado: "I. DOS FATOS", "II – Da legitimidade", "3. DO PEDIDO", "II.2 ADVOCACIA"
_NUM = r"(?:X{0,3}(?:IX|IV|V?I{1,3}|V|X)|[1-9]\d?)"  # I a XXXIX, ou 1 a 99
RE_TITULO_COM_SEPARADOR = re.compile(
    rf"^(?P<num>{_NUM})(?:\.\d{{1,2}}){{0,3}}\s*[.\-–—)](?P<esp>\s*)(?P<resto>[^\W\d_].*)$"
)
RE_TITULO_COM_SUBNUMERO = re.compile(rf"^{_NUM}(?:\.\d{{1,2}}){{1,3}}\s+(?P<resto>[^\W\d_].*)$")
RE_INICIO_PARAGRAFO = re.compile(r"^(\d{1,3}[.)]|[a-z]\))\s+\S")
PRONOMES_ENCLITICOS = {
    "se", "me", "te", "lhe", "lhes", "nos", "vos",
    "o", "a", "os", "as", "lo", "la", "los", "las", "no", "na", "nos", "nas",
}


@dataclass(frozen=True)
class Linha:
    texto: str  # "" representa linha em branco
    pagina: int
    metodo: str


@dataclass(frozen=True)
class Bloco:
    texto: str
    tipo: str  # "titulo" ou "paragrafo"
    pagina_inicio: int
    pagina_fim: int
    metodos: frozenset[str]


def normalizar(texto: str) -> str:
    """Normaliza Unicode e espaços de uma linha, sem mexer em acentos ou caixa."""
    texto = unicodedata.normalize("NFC", texto).translate(_TABELA_TROCAS)
    return re.sub(r"[ \t]+", " ", texto).strip()


def eh_ruido(linha: str) -> bool:
    """Número de página, carimbo de assinatura ou linha sem conteúdo alfanumérico."""
    if any(r.search(linha) for r in RE_RUIDO):
        return True
    sem_espaco = linha.replace(" ", "")
    if len(sem_espaco) >= 5:
        alfanum = sum(c.isalnum() for c in sem_espaco)
        if alfanum / len(sem_espaco) < 0.5:
            return True
    return False


def _chave(linha: str) -> str:
    return re.sub(r"\d+", "#", linha.lower())


def linhas_repetidas(paginas_normalizadas: list[list[str]]) -> set[str]:
    """Chaves de linhas que aparecem em pelo menos metade das páginas (cabeçalho/rodapé)."""
    com_texto = [p for p in paginas_normalizadas if any(p)]
    if len(com_texto) < 4:
        return set()
    contagem: Counter[str] = Counter()
    for linhas in com_texto:
        contagem.update({_chave(l) for l in linhas if len(l) >= 4})
    minimo = max(3, len(com_texto) / 2)
    return {chave for chave, n in contagem.items() if n >= minimo}


def eh_pagina_de_sumario(linhas: list[str]) -> bool:
    return sum(bool(RE_PONTILHADO_SUMARIO.search(l)) for l in linhas) >= 3


def limpar_paginas(paginas: list[Pagina]) -> list[Linha]:
    """Devolve as linhas úteis do arquivo, em ordem, com página e método de origem."""
    normalizadas = [[normalizar(l) for l in p.texto.split("\n")] for p in paginas]
    repetidas = linhas_repetidas(normalizadas)
    saida: list[Linha] = []
    for pagina, linhas in zip(paginas, normalizadas):
        if pagina.metodo == "vazia" or eh_pagina_de_sumario(linhas):
            continue
        for texto in linhas:
            if texto == "":
                saida.append(Linha("", pagina.numero, pagina.metodo))
            elif _chave(texto) in repetidas or eh_ruido(texto):
                continue
            else:
                saida.append(Linha(texto, pagina.numero, pagina.metodo))
        saida.append(Linha("", pagina.numero, pagina.metodo))
    return saida
