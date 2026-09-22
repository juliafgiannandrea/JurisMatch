"""
Mede o erro REAL do OCR, com gabarito, sem transcrição manual.

A ideia: as páginas que têm camada de texto nativo já trazem o texto exato do
documento. Então dá para usar essas páginas como gabarito — basta rasterizá-las
como imagem, jogar no OCR e comparar o que voltou com o texto que já se sabia
estar correto. Isso dá CER e WER medidos, sobre este corpus, sem anotar nada
à mão.

  CER (Character Error Rate) = distância de edição / nº de caracteres do gabarito
  WER (Word Error Rate)      = distância de edição em palavras / nº de palavras

Limite honesto do método: páginas nativas rasterizadas são digitalizações
"limpas". Digitalizações reais têm ruído, inclinação, manchas e papel amarelado,
então o erro medido aqui é um PISO — o OCR sobre escaneados de verdade erra mais.
Serve para comparar configurações (DPI, PSM, idioma) e para comparar soluções
entre si em pé de igualdade, não para prever o erro absoluto nos escaneados.

Uso:
    python benchmark_ocr.py --paginas 40
    python benchmark_ocr.py --dpi 150 --dpi 200 --dpi 300     # compara resoluções
    python benchmark_ocr.py --idioma por --idioma eng         # mostra o ganho do pacote pt

Instalação:
    pip install pymupdf rapidfuzz     # rapidfuzz é opcional, acelera a distância
    sudo apt install tesseract-ocr tesseract-ocr-por
"""

import argparse
import csv
import random
import re
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import pymupdf

try:
    from rapidfuzz.distance import Levenshtein as _Lev
    def distancia(a, b):
        return _Lev.distance(a, b)
    MOTOR = "rapidfuzz"
except ImportError:                                   # fallback sem dependência
    def distancia(a, b):
        if a == b:
            return 0
        if not a:
            return len(b)
        if not b:
            return len(a)
        anterior = list(range(len(b) + 1))
        for i, ca in enumerate(a, start=1):
            atual = [i]
            for j, cb in enumerate(b, start=1):
                atual.append(min(anterior[j] + 1, atual[j - 1] + 1,
                                 anterior[j - 1] + (ca != cb)))
            anterior = atual
        return anterior[-1]
    MOTOR = "python puro (lento; instale rapidfuzz)"

# ============================ CONFIGURAÇÃO ============================
PASTA_PDFS = "../scrapping_processos_controle_concentrado/peticoes_processos_estruturantes"
MIN_CHARS_GABARITO = 800       # só páginas densas servem de gabarito
PSM = 3
TIMEOUT_OCR = 180
SEMENTE = 42                   # amostragem reprodutível
RE_PALAVRA = re.compile(r"[^\W\d_]+", re.UNICODE)
# ======================================================================


def normalizar(t: str) -> str:
    """Normalização mínima, igual para gabarito e OCR, para não premiar nem punir ninguém."""
    t = t.replace("\xad", "").replace(" ", " ")
    t = re.sub(r"[ \t\n]+", " ", t)
    return t.strip()


def palavras(t: str):
    return normalizar(t).split()


def wer(ref: str, hip: str) -> float:
    """Distância de edição em nível de palavra, normalizada."""
    r, h = palavras(ref), palavras(hip)
    if not r:
        return 0.0 if not h else 1.0
    # mapeia cada palavra única para um caractere, e reusa a distância de caractere
    vocab = {w: chr(i + 256) for i, w in enumerate(dict.fromkeys(r + h))}
    return distancia("".join(vocab[w] for w in r), "".join(vocab[w] for w in h)) / len(r)


def cer(ref: str, hip: str) -> float:
    r, h = normalizar(ref), normalizar(hip)
    if not r:
        return 0.0 if not h else 1.0
    return distancia(r, h) / len(r)


def sacola(ref: str, hip: str):
    """Recall, precisão e F1 no nível de palavra, IGNORANDO a ordem.

    Existe porque CER e WER punem diferença de ordem de leitura como se fosse
    erro de reconhecimento. Neste corpus isso acontece muito: a tarja de
    assinatura digital do STF é texto vertical na margem, e o extrator nativo a
    insere no meio do fluxo, enquanto o OCR a põe em outro lugar. O bloco inteiro
    fica deslocado e a distância de edição dispara, mesmo com as palavras todas
    corretas. Comparar as duas famílias de métrica separa um problema do outro:
      CER alto + F1 alto  -> ordem de leitura diferente, reconhecimento bom
      CER alto + F1 baixo -> reconhecimento ruim de verdade
    """
    r = Counter(w.lower() for w in RE_PALAVRA.findall(normalizar(ref)))
    h = Counter(w.lower() for w in RE_PALAVRA.findall(normalizar(hip)))
    if not r:
        return (1.0, 1.0, 1.0) if not h else (0.0, 0.0, 0.0)
    comum = sum((r & h).values())
    rec = comum / sum(r.values())
    prec = comum / max(sum(h.values()), 1)
    f1 = 2 * rec * prec / (rec + prec) if (rec + prec) else 0.0
    return rec, prec, f1


def ocr(pagina, dpi: int, idioma: str) -> str:
    png = pagina.get_pixmap(dpi=dpi).tobytes("png")
    p = subprocess.run(["tesseract", "stdin", "stdout", "-l", idioma, "--psm", str(PSM)],
                       input=png, capture_output=True, timeout=TIMEOUT_OCR)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[-200:])
    return p.stdout.decode("utf-8", "replace")


def sortear_paginas(pasta, quantas, semente):
    """Sorteia páginas com texto nativo denso, espalhadas por documentos diferentes."""
    rnd = random.Random(semente)
    pdfs = sorted(Path(pasta).glob("*.pdf"))
    rnd.shuffle(pdfs)
    escolhidas = []
    for pdf in pdfs:
        if len(escolhidas) >= quantas:
            break
        try:
            doc = pymupdf.open(pdf)
        except Exception:
            continue
        candidatas = []
        for i, pag in enumerate(doc):
            txt = pag.get_text(sort=True)
            if len(re.sub(r"\s", "", txt)) >= MIN_CHARS_GABARITO:
                candidatas.append(i)
        if candidatas:                                # no máximo 2 por documento
            for i in rnd.sample(candidatas, min(2, len(candidatas))):
                escolhidas.append((str(pdf), i))
                if len(escolhidas) >= quantas:
                    break
        doc.close()
    return escolhidas[:quantas]


def main():
    ap = argparse.ArgumentParser(
        description="Mede CER e WER do OCR usando páginas de texto nativo como gabarito.")
    ap.add_argument("-e", "--entrada", default=PASTA_PDFS, help="pasta com os PDFs")
    ap.add_argument("-n", "--paginas", type=int, default=30, help="quantas páginas amostrar")
    ap.add_argument("--dpi", type=int, action="append", help="resolução; repita para comparar")
    ap.add_argument("--idioma", action="append", help="idioma do tesseract; repita para comparar")
    ap.add_argument("--semente", type=int, default=SEMENTE, help="semente da amostragem")
    ap.add_argument("--csv", default="benchmark_ocr.csv", help="CSV com o resultado por página")
    args = ap.parse_args()

    dpis = args.dpi or [300]
    idiomas = args.idioma or ["por"]

    if not Path(args.entrada).is_dir():
        sys.exit(f"ERRO: pasta não existe: {args.entrada}")
    try:
        subprocess.run(["tesseract", "--version"], capture_output=True, timeout=30)
    except FileNotFoundError:
        sys.exit("ERRO: tesseract não encontrado.\n"
                 "    sudo apt install tesseract-ocr tesseract-ocr-por")

    print(f"Sorteando {args.paginas} páginas com texto nativo denso (semente {args.semente})...")
    amostra = sortear_paginas(args.entrada, args.paginas, args.semente)
    if not amostra:
        sys.exit("ERRO: nenhuma página nativa densa encontrada na pasta.")
    docs = len({a for a, _ in amostra})
    print(f"  {len(amostra)} páginas de {docs} documento(s) distintos")
    print(f"  motor de distância: {MOTOR}\n")

    linhas, resumo = [], {}
    for idioma in idiomas:
        for dpi in dpis:
            chave = f"{idioma} @ {dpi} DPI"
            cers, wers, f1s, recs, precs, tempos = [], [], [], [], [], []
            print(f"--- {chave} ---")
            for k, (caminho, i) in enumerate(amostra, start=1):
                doc = pymupdf.open(caminho)
                pagina = doc[i]
                gabarito = pagina.get_text(sort=True)
                try:
                    t0 = time.perf_counter()
                    saida = ocr(pagina, dpi, idioma)
                    dt = time.perf_counter() - t0
                except Exception as e:  # noqa: BLE001
                    print(f"  [{k}/{len(amostra)}] {Path(caminho).stem} p.{i+1}: FALHOU — {e}")
                    doc.close()
                    continue
                doc.close()
                c, w = cer(gabarito, saida), wer(gabarito, saida)
                rec, prec, f1 = sacola(gabarito, saida)
                cers.append(c); wers.append(w); tempos.append(dt)
                recs.append(rec); precs.append(prec); f1s.append(f1)
                linhas.append({"config": chave, "arquivo": Path(caminho).stem, "pagina": i + 1,
                               "chars_gabarito": len(normalizar(gabarito)),
                               "cer": round(c, 4), "wer": round(w, 4),
                               "recall": round(rec, 4), "precisao": round(prec, 4),
                               "f1": round(f1, 4), "segundos": round(dt, 2)})
                print(f"  [{k}/{len(amostra)}] {Path(caminho).stem} p.{i+1}: "
                      f"CER {c:6.2%}  WER {w:6.2%}  F1 {f1:6.2%}  {dt:.1f}s")
            if cers:
                resumo[chave] = {
                    "paginas": len(cers),
                    "cer_medio": statistics.mean(cers),
                    "cer_mediana": statistics.median(cers),
                    "cer_p90": sorted(cers)[int(len(cers) * 0.9) - 1] if len(cers) >= 10 else max(cers),
                    "wer_medio": statistics.mean(wers),
                    "wer_mediana": statistics.median(wers),
                    "recall_medio": statistics.mean(recs),
                    "precisao_media": statistics.mean(precs),
                    "f1_medio": statistics.mean(f1s),
                    "f1_mediana": statistics.median(f1s),
                    "seg_por_pagina": statistics.mean(tempos),
                }
            print()

    print("=" * 100)
    print("RESUMO — OCR contra texto nativo como gabarito")
    print("=" * 100)
    print("\nSENSÍVEL À ORDEM DE LEITURA (distância de edição)")
    print(f"{'configuração':<22}{'págs':>6}{'CER médio':>12}{'CER mediana':>13}"
          f"{'CER p90':>10}{'WER médio':>12}{'WER mediana':>13}{'s/página':>11}")
    for chave, v in resumo.items():
        print(f"{chave:<22}{v['paginas']:>6}{v['cer_medio']:>12.2%}{v['cer_mediana']:>13.2%}"
              f"{v['cer_p90']:>10.2%}{v['wer_medio']:>12.2%}{v['wer_mediana']:>13.2%}"
              f"{v['seg_por_pagina']:>11.2f}")
    print("\nINSENSÍVEL À ORDEM (palavras reconhecidas, sacola de palavras)")
    print(f"{'configuração':<22}{'págs':>6}{'recall':>12}{'precisão':>13}"
          f"{'F1 médio':>12}{'F1 mediana':>13}")
    for chave, v in resumo.items():
        print(f"{chave:<22}{v['paginas']:>6}{v['recall_medio']:>12.2%}{v['precisao_media']:>13.2%}"
              f"{v['f1_medio']:>12.2%}{v['f1_mediana']:>13.2%}")
    print()
    print("Como ler as duas tabelas juntas:")
    print("  CER alto + F1 alto  -> ordem de leitura diferente, reconhecimento bom")
    print("  CER alto + F1 baixo -> reconhecimento ruim de verdade")
    print("Neste corpus a tarja de assinatura digital do STF é texto vertical na margem")
    print("e desloca blocos inteiros, então o CER costuma exagerar o erro.")
    print()
    print("Lembrete: são páginas nativas rasterizadas, ou seja, digitalizações limpas.")
    print("O erro em escaneados reais é maior. Use estes números para comparar")
    print("configurações e soluções, não como previsão do erro absoluto.")

    if linhas:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(linhas[0]), delimiter=";")
            w.writeheader()
            w.writerows(linhas)
        print(f"\nDetalhe por página em {args.csv}")


if __name__ == "__main__":
    main()
