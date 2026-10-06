"""Empacota blocos (títulos e parágrafos) em chunks com metadados.

Regras: um chunk nunca mistura seções; parágrafos consecutivos são agrupados até o
alvo de tokens; só parágrafos maiores que o teto são quebrados (por sentença).
"""
from __future__ import annotations

import hashlib
import re
from typing import Callable

from jurismatch.config import ALVO_TOKENS, TETO_TOKENS, VERSAO_PIPELINE
from jurismatch.limpeza import MAIUSCULAS, Bloco

ContarTokens = Callable[[str], int]

RE_FIM_SENTENCA = re.compile(rf"(?<=[.!?;])\s+(?=[{MAIUSCULAS}\"“(\d])")
# Abreviações cujo ponto final não encerra a sentença
RE_ABREVIACAO = re.compile(
    r"(?:\b(?:arts?|fls?|n|nº|inc|incs|al|p|pp|cf|v|vol|ed|op|cit|obs|ex|rel|min|des|dr|dra|drs|sr|sra|srs|"
    r"exa|exas|exmo|exma|ilmo|prof|profa|proc|doc|docs|j|julg|dj|dje|i\.e|e\.g)|\b[A-Z])\.$",
    re.IGNORECASE,
)
MAX_SECAO = 120


def dividir_em_sentencas(texto: str) -> list[str]:
    """Divide em sentenças sem quebrar em abreviações jurídicas como 'art.' e 'fls.'."""
    sentencas: list[str] = []
    for parte in RE_FIM_SENTENCA.split(texto):
        if sentencas and RE_ABREVIACAO.search(sentencas[-1]):
            sentencas[-1] += " " + parte
        else:
            sentencas.append(parte)
    return sentencas


def cabecalho(classe: str, numero: int, secao: str) -> str:
    """Contexto prefixado ao chunk antes de embedar: identifica a petição e a seção."""
    base = f"{classe} {numero}"
    return f"{base} | {secao}" if secao else base


def _fatiar(texto: str, limite: int, contar: ContarTokens) -> list[str]:
    """Quebra um texto maior que `limite` em pedaços de sentenças (ou palavras)."""
    pedacos: list[str] = []
    atual = ""
    for sentenca in dividir_em_sentencas(texto):
        if contar(sentenca) > limite:
            unidades = sentenca.split(" ")  # sentença gigante: cai para palavras
        else:
            unidades = [sentenca]
        for unidade in unidades:
            candidato = f"{atual} {unidade}" if atual else unidade
            if atual and contar(candidato) > limite:
                pedacos.append(atual)
                atual = unidade
            else:
                atual = candidato
    if atual:
        pedacos.append(atual)
    return pedacos


def _metodo(metodos: frozenset[str]) -> str:
    return next(iter(metodos)) if len(metodos) == 1 else "misto"


def gerar_chunks(
    blocos: list[Bloco],
    *,
    doc_id: str,
    classe: str,
    numero: int,
    arquivo_pdf: str,
    contar_tokens: ContarTokens,
    alvo: int = ALVO_TOKENS,
    teto: int = TETO_TOKENS,
    indice_inicial: int = 0,
    secao_inicial: str = "",
) -> tuple[list[dict], str]:
    """Devolve (chunks, seção vigente ao final) para os blocos de um arquivo."""
    chunks: list[dict] = []
    secao = secao_inicial
    buffer: list[Bloco] = []
    secao_do_buffer = secao

    def limite_de_texto(s: str) -> int:
        return teto - contar_tokens(cabecalho(classe, numero, s)) - 2

    def tokens_do_buffer() -> int:
        return contar_tokens("\n\n".join(b.texto for b in buffer)) if buffer else 0

    def fechar():
        nonlocal buffer
        if not buffer:
            return
        texto = "\n\n".join(b.texto for b in buffer)
        buffer_atual, buffer = buffer, []
        if sum(c.isalpha() for c in texto) < 20:
            return  # resto de ruído, sem conteúdo
        texto_embedding = f"{cabecalho(classe, numero, secao_do_buffer)}\n{texto}"
        metodos = frozenset().union(*(b.metodos for b in buffer_atual))
        chunks.append(
            {
                "chunk_id": f"{doc_id}_{indice_inicial + len(chunks):04d}",
                "doc_id": doc_id,
                "classe": classe,
                "numero": numero,
                "arquivo_pdf": arquivo_pdf,
                "pagina_inicio": buffer_atual[0].pagina_inicio,
                "pagina_fim": buffer_atual[-1].pagina_fim,
                "metodo_extracao": _metodo(metodos),
                "secao": secao_do_buffer,
                "n_tokens": contar_tokens(texto_embedding),
                "texto": texto,
                "texto_embedding": texto_embedding,
                "hash": hashlib.sha1(texto_embedding.encode("utf-8")).hexdigest(),
                "versao_pipeline": VERSAO_PIPELINE,
            }
        )

    for bloco in blocos:
        if bloco.tipo == "titulo":
            so_titulos = all(b.tipo == "titulo" for b in buffer)
            if not so_titulos or tokens_do_buffer() + contar_tokens(bloco.texto) > alvo:
                fechar()
            secao = bloco.texto[:MAX_SECAO]
            secao_do_buffer = secao
            buffer.append(bloco)
            continue
        if not buffer:
            secao_do_buffer = secao
        limite = limite_de_texto(secao_do_buffer)
        if contar_tokens(bloco.texto) > limite:
            # Parágrafo maior que o teto: fecha o que havia e quebra por sentença
            so_titulos = bool(buffer) and all(b.tipo == "titulo" for b in buffer)
            reserva = tokens_do_buffer() if so_titulos else 0
            if not so_titulos:
                fechar()
            for pedaco in _fatiar(bloco.texto, limite - reserva, contar_tokens):
                buffer.append(
                    Bloco(pedaco, "paragrafo", bloco.pagina_inicio, bloco.pagina_fim, bloco.metodos)
                )
                secao_do_buffer = secao
                fechar()
            continue
        so_titulos = bool(buffer) and all(b.tipo == "titulo" for b in buffer)
        novo_total = contar_tokens("\n\n".join([b.texto for b in buffer] + [bloco.texto]))
        if buffer and (novo_total > limite or (novo_total > alvo and not so_titulos)):
            fechar()
            secao_do_buffer = secao
        buffer.append(bloco)
    fechar()
    return chunks, secao
