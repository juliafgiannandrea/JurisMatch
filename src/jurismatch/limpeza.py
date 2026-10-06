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


def _proporcao_maiusculas(texto: str) -> float:
    letras = [c for c in texto if c.isalpha()]
    if len(letras) < 4:
        return 0.0
    return sum(c.isupper() for c in letras) / len(letras)


def termina_frase(texto: str) -> bool:
    return texto.rstrip("\"'”’»)]").endswith((".", "!", "?", ":", ";"))


def eh_titulo(linha: str, anterior_terminou: bool) -> bool:
    """Título de seção: numeração (romana ou arábica) seguida de texto em maiúsculas,
    ou numeral romano + travessão + título curto em caixa mista."""
    if len(linha) > 160 or linha.endswith((",", ";")):
        return False
    m = RE_TITULO_COM_SEPARADOR.match(linha)
    if m is None:
        m = RE_TITULO_COM_SUBNUMERO.match(linha)
        return bool(m) and _proporcao_maiusculas(m.group("resto")) >= 0.8
    if _proporcao_maiusculas(m.group("resto")) >= 0.8:
        return True
    return (
        anterior_terminou
        and m.group("num")[0] in "IVXL"
        and bool(m.group("esp"))
        and m.group("resto")[0].isupper()
        and len(linha) <= 80
        and len(linha.split()) <= 10
        and "," not in linha
        and not linha.endswith((".", ":"))
    )


def eh_destaque(linha: str) -> bool:
    """Linha curta toda em maiúsculas (endereçamento, nome da ação, timbre)."""
    return len(linha) <= 160 and len(linha.split()) <= 20 and _proporcao_maiusculas(linha) >= 0.9


def _juntar(anterior: str, proxima: str) -> str:
    """Rejunta duas linhas do mesmo parágrafo, desfazendo hifenização de fim de linha."""
    if anterior.endswith("-") and len(anterior) > 1 and anterior[-2].isalnum():
        primeira = re.match(r"\w+", proxima)
        palavra = primeira.group(0).lower() if primeira else ""
        if proxima[0].isdigit() or palavra in PRONOMES_ENCLITICOS:
            return anterior + proxima  # "80.540-" + "290", "declara-" + "se"
        if proxima[0].islower():
            return anterior[:-1] + proxima  # "constitu-" + "cional"
    return anterior + " " + proxima


def montar_blocos(linhas: list[Linha]) -> list[Bloco]:
    """Agrupa linhas em parágrafos e títulos, preservando o intervalo de páginas."""
    blocos: list[Bloco] = []
    texto = ""
    pag_ini = pag_fim = 0
    metodos: set[str] = set()
    houve_branco = True
    em_destaque = False  # o parágrafo aberto é um bloco de linhas em maiúsculas
    titulo_aberto = False  # a linha anterior foi um título (pode continuar na próxima)

    def fechar():
        nonlocal texto, metodos
        if texto:
            blocos.append(Bloco(texto, "paragrafo", pag_ini, pag_fim, frozenset(metodos)))
        texto, metodos = "", set()

    for linha in linhas:
        if linha.texto == "":
            houve_branco = True
            titulo_aberto = False
            continue
        t = linha.texto
        anterior_terminou = texto == "" or em_destaque or termina_frase(texto)
        destaque = eh_destaque(t)

        # Título em caixa mista só é aceito depois de ponto final (incisos de lei vêm depois de
        # ":" ou ";") e em página nativa (em OCR, anexos digitalizados geram falsos títulos).
        apos_ponto = texto == "" or em_destaque or texto.rstrip("\"'”’»)]").endswith((".", "!", "?"))
        if eh_titulo(t, apos_ponto and linha.metodo == "nativo"):
            fechar()
            blocos.append(Bloco(t, "titulo", linha.pagina, linha.pagina, frozenset({linha.metodo})))
            titulo_aberto, em_destaque, houve_branco = True, False, False
            continue
        if titulo_aberto and destaque and len(blocos[-1].texto) < 300:
            ant = blocos.pop()  # título quebrado em duas linhas
            blocos.append(
                Bloco(f"{ant.texto} {t}", "titulo", ant.pagina_inicio, linha.pagina, ant.metodos | {linha.metodo})
            )
            houve_branco = False
            continue
        titulo_aberto = False

        if destaque and anterior_terminou:
            novo = not em_destaque
            em_destaque = True
        elif em_destaque:
            novo, em_destaque = True, False
        else:
            novo = (
                texto == ""
                or bool(RE_INICIO_PARAGRAFO.match(t))
                or (houve_branco and termina_frase(texto) and not t[0].islower())
            )
        if novo:
            fechar()
            texto, pag_ini = t, linha.pagina
        else:
            texto = _juntar(texto, t)
        pag_fim = linha.pagina
        metodos.add(linha.metodo)
        houve_branco = False
    fechar()
    return blocos
