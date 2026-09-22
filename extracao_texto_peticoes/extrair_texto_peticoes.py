"""
Extrai o texto das petições iniciais do STF baixadas na etapa 1.

Estratégia (calibrada sobre os 102 PDFs já coletados, 4.536 páginas):
  - 58% das páginas têm texto nativo -> PyMuPDF extrai o texto exato, rápido.
  - 42% são digitalizações sem camada de texto -> precisam de OCR (tesseract).
  - 6 dos 102 documentos são MISTOS: têm páginas nativas e escaneadas no mesmo
    arquivo. Por isso a decisão é tomada PÁGINA A PÁGINA, nunca por documento.
  - A data de autuação não prevê nada: ADC 96 e ADC 98, ambas de 2025, vieram
    inteiramente escaneadas. Não dá para filtrar candidatos a OCR por ano.

Critério de decisão por página:
    texto nativo >= MIN_CHARS                  -> usa o texto do PDF
    texto < MIN_CHARS e imagem cobrindo a pág. -> OCR
    texto < MIN_CHARS e sem imagem grande      -> página vazia / só assinatura
A segunda condição é necessária: páginas de assinatura e de fecho têm pouco texto
e nenhuma imagem grande. Sem ela, o OCR rodaria nelas e não devolveria nada.

Custo: a cobertura de imagem só é calculada nas páginas com pouco texto, e via
page.get_image_info(), que mediu 35x a 465x mais rápido que get_text("dict")
(este último decodifica os bytes da imagem, aquele lê só a bounding box).

Instalação (uma vez):
    pip install pymupdf
    sudo apt install tesseract-ocr tesseract-ocr-por

Uso:
    python extrair_texto_peticoes.py
    python extrair_texto_peticoes.py --sem-ocr        # passada rápida, só nativo
    python extrair_texto_peticoes.py --limite 5       # testa em 5 arquivos
"""

import argparse
import csv
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pymupdf

# ============================ CONFIGURAÇÃO ============================
PASTA_PDFS = "../scrapping_processos_controle_concentrado/peticoes_processos_estruturantes"
PASTA_SAIDA = "texto_peticoes"    # onde os .txt e o log serão gravados
MIN_CHARS = 100                   # menos que isso na página = não há texto nativo útil
MIN_COBERTURA_IMG = 0.5           # fração da página coberta por imagem para considerar digitalização
DPI = 300                         # resolução de rasterização para o OCR (recomendada pelo tesseract)
IDIOMA_OCR = "por"                # pacote tesseract-ocr-por
PSM = 3                           # page segmentation mode 3 = automático, bom para documentos
TIMEOUT_OCR = 120                 # segundos por página antes de desistir do OCR
PROCESSOS = 0                     # 0 = usa todos os núcleos disponíveis
MARCADORES_PAGINA = True          # grava "[[pagina N | metodo]]" antes de cada página
PULAR_JA_EXTRAIDOS = True         # não reprocessa arquivos que já têm .txt
# ======================================================================

MARCADOR = "[[pagina {n} | {metodo}]]"
RE_MARCADOR = re.compile(r"^\[\[pagina \d+ \| \w+\]\]$", re.MULTILINE)


# ------------------------------------------------------------------ texto

def normalizar(texto: str) -> str:
    """Limpa o texto sem alterar o conteúdo: espaços, hífen suave, linhas em branco."""
    if not texto:
        return ""
    texto = texto.replace("\xad", "")                  # hífen suave invisível
    texto = texto.replace(" ", " ")               # espaço não separável
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = "\n".join(linha.strip() for linha in texto.splitlines())
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def limpar_marcadores(texto: str) -> str:
    """Remove os marcadores de página. Útil para quem for consumir o .txt puro."""
    return re.sub(r"\n{3,}", "\n\n", RE_MARCADOR.sub("", texto)).strip()


# --------------------------------------------------------------- páginas

def cobertura_imagem(pagina) -> float:
    """Fração da área da página coberta por imagens (0.0 a 1.0)."""
    area_pagina = abs(pagina.rect.width * pagina.rect.height)
    if area_pagina <= 0:
        return 0.0
    area_img = 0.0
    try:
        for img in pagina.get_image_info():
            x0, y0, x1, y1 = img["bbox"]
            area_img += abs((x1 - x0) * (y1 - y0))
    except Exception:
        return 0.0
    return min(area_img / area_pagina, 1.0)


def ocr_pagina(pagina, dpi: int, idioma: str, psm: int, timeout: int) -> str:
    """Rasteriza a página e passa o PNG para o tesseract pela entrada padrão."""
    png = pagina.get_pixmap(dpi=dpi).tobytes("png")
    proc = subprocess.run(
        ["tesseract", "stdin", "stdout", "-l", idioma, "--psm", str(psm)],
        input=png, capture_output=True, timeout=timeout,
    )
    if proc.returncode != 0:
        erro = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(f"tesseract falhou: {erro[-1] if erro else 'sem mensagem'}")
    return proc.stdout.decode("utf-8", "replace")


def processar_pdf(caminho: str, cfg: dict) -> dict:
    """Extrai o texto de um PDF inteiro. Roda num processo separado."""
    nome = os.path.basename(caminho)
    reg = {"arquivo": nome, "paginas": 0, "pags_nativas": 0, "pags_ocr": 0,
           "pags_vazias": 0, "chars": 0, "metodo": "", "segundos": 0.0,
           "status": "", "obs": ""}
    t0 = time.perf_counter()

    try:
        doc = pymupdf.open(caminho)
    except Exception as e:
        reg.update(status="erro", obs=f"não abriu: {e}"[:200])
        return reg

    partes, falhas_ocr = [], 0
    try:
        for i, pagina in enumerate(doc, start=1):
            # 1. tenta o texto nativo (sort=True devolve na ordem de leitura)
            try:
                texto = pagina.get_text(sort=True, flags=pymupdf.TEXT_DEHYPHENATE)
            except Exception:
                texto = ""
            chars = len(re.sub(r"\s", "", texto))

            if chars >= cfg["min_chars"]:
                metodo = "nativo"
                reg["pags_nativas"] += 1
            elif cfg["sem_ocr"]:
                # passada rápida: não roda OCR, só marca o que precisaria
                metodo = "pendente" if cobertura_imagem(pagina) >= cfg["min_cob"] else "vazia"
                reg["pags_ocr" if metodo == "pendente" else "pags_vazias"] += 1
                texto = ""
            elif cobertura_imagem(pagina) >= cfg["min_cob"]:
                # 2. página digitalizada: OCR
                try:
                    texto = ocr_pagina(pagina, cfg["dpi"], cfg["idioma"],
                                       cfg["psm"], cfg["timeout"])
                    metodo = "ocr"
                    reg["pags_ocr"] += 1
                except (subprocess.TimeoutExpired, RuntimeError, Exception) as e:  # noqa: BLE001
                    texto, metodo = "", "ocr_falhou"
                    falhas_ocr += 1
                    reg["pags_vazias"] += 1
                    if not reg["obs"]:
                        reg["obs"] = f"OCR falhou na pág. {i}: {e}"[:150]
            else:
                # 3. página em branco, de assinatura ou de fecho
                metodo = "vazia"
                reg["pags_vazias"] += 1

            texto = normalizar(texto)
            if cfg["marcadores"]:
                partes.append(MARCADOR.format(n=i, metodo=metodo))
            if texto:
                partes.append(texto)
            reg["paginas"] += 1
    finally:
        doc.close()

    conteudo = "\n\n".join(partes).strip() + "\n"
    destino = Path(cfg["saida"]) / (Path(nome).stem + ".txt")
    destino.write_text(conteudo, encoding="utf-8")

    reg["chars"] = len(RE_MARCADOR.sub("", conteudo).replace("\n", ""))
    if reg["pags_ocr"] and reg["pags_nativas"]:
        reg["metodo"] = "misto"
    elif reg["pags_ocr"]:
        reg["metodo"] = "ocr"
    elif reg["pags_nativas"]:
        reg["metodo"] = "nativo"
    else:
        reg["metodo"] = "vazio"
    reg["segundos"] = round(time.perf_counter() - t0, 1)
    reg["status"] = "ok" if not falhas_ocr else "ok_com_falhas"
    return reg


# ------------------------------------------------------------------ main

def verificar_tesseract(idioma: str) -> None:
    try:
        r = subprocess.run(["tesseract", "--list-langs"], capture_output=True, timeout=30)
    except FileNotFoundError:
        sys.exit("ERRO: tesseract não encontrado. Instale com:\n"
                 "    sudo apt install tesseract-ocr tesseract-ocr-por")
    langs = r.stdout.decode("utf-8", "replace").split()
    if idioma not in langs:
        sys.exit(f"ERRO: idioma '{idioma}' não instalado no tesseract (tem: {', '.join(langs)}).\n"
                 f"    sudo apt install tesseract-ocr-{idioma}")


def main():
    ap = argparse.ArgumentParser(description="Extrai texto das petições iniciais do STF.")
    ap.add_argument("-e", "--entrada", default=PASTA_PDFS, help="pasta com os PDFs")
    ap.add_argument("-o", "--saida", default=PASTA_SAIDA, help="pasta de destino dos .txt")
    ap.add_argument("-j", "--processos", type=int, default=PROCESSOS,
                    help="processos paralelos (0 = todos os núcleos)")
    ap.add_argument("--limite", type=int, default=0, help="processa só os N primeiros PDFs")
    ap.add_argument("--dpi", type=int, default=DPI)
    ap.add_argument("--idioma", default=IDIOMA_OCR)
    ap.add_argument("--min-chars", type=int, default=MIN_CHARS)
    ap.add_argument("--min-cobertura", type=float, default=MIN_COBERTURA_IMG)
    ap.add_argument("--sem-ocr", action="store_true",
                    help="passada rápida: só texto nativo, marca as páginas que precisariam de OCR")
    ap.add_argument("--sem-marcadores", action="store_true",
                    help="não grava as linhas [[pagina N | metodo]] no .txt")
    ap.add_argument("--forcar", action="store_true", help="reprocessa mesmo o que já tem .txt")
    args = ap.parse_args()

    if not args.sem_ocr:
        verificar_tesseract(args.idioma)

    entrada = Path(args.entrada)
    if not entrada.is_dir():
        sys.exit(f"ERRO: pasta de entrada não existe: {entrada.resolve()}")
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(str(p) for p in entrada.glob("*.pdf"))
    if PULAR_JA_EXTRAIDOS and not args.forcar:
        pdfs = [p for p in pdfs if not (saida / (Path(p).stem + ".txt")).exists()]
    if args.limite:
        pdfs = pdfs[:args.limite]

    if not pdfs:
        print("Nada a fazer: todos os PDFs já têm .txt (use --forcar para reprocessar).")
        return

    n_proc = args.processos or os.cpu_count() or 1
    cfg = {"saida": str(saida), "min_chars": args.min_chars, "min_cob": args.min_cobertura,
           "dpi": args.dpi, "idioma": args.idioma, "psm": PSM, "timeout": TIMEOUT_OCR,
           "marcadores": MARCADORES_PAGINA and not args.sem_marcadores,
           "sem_ocr": args.sem_ocr}

    print(f"Extraindo {len(pdfs)} PDF(s) com {n_proc} processo(s) para '{saida}/'")
    print(f"  OCR: {'desligado' if args.sem_ocr else f'tesseract -l {args.idioma} a {args.dpi} DPI'}")
    print(f"  critério: pág. com <{args.min_chars} chars e >={args.min_cobertura:.0%} de imagem = digitalizada\n")

    # tesseract usa OpenMP e por padrão abre várias threads; com um processo por
    # núcleo isso gera concorrência excessiva e fica mais lento.
    os.environ["OMP_THREAD_LIMIT"] = "1"

    t0 = time.perf_counter()
    linhas = []
    with ProcessPoolExecutor(max_workers=n_proc) as ex:
        futuros = {ex.submit(processar_pdf, p, cfg): p for p in pdfs}
        for k, fut in enumerate(as_completed(futuros), start=1):
            try:
                reg = fut.result()
            except Exception as e:  # noqa: BLE001
                nome = os.path.basename(futuros[fut])
                reg = {"arquivo": nome, "paginas": 0, "pags_nativas": 0, "pags_ocr": 0,
                       "pags_vazias": 0, "chars": 0, "metodo": "", "segundos": 0.0,
                       "status": "erro", "obs": str(e)[:200]}
            linhas.append(reg)
            print(f"[{k}/{len(pdfs)}] {reg['arquivo']}: {reg['metodo']} — "
                  f"{reg['paginas']} pág. ({reg['pags_nativas']} nativas, {reg['pags_ocr']} OCR, "
                  f"{reg['pags_vazias']} vazias), {reg['chars']} chars, {reg['segundos']}s"
                  + (f" — {reg['obs']}" if reg["obs"] else ""))

    linhas.sort(key=lambda r: r["arquivo"])
    campos = ["arquivo", "paginas", "pags_nativas", "pags_ocr", "pags_vazias",
              "chars", "metodo", "segundos", "status", "obs"]
    log = saida / "log_extracao.csv"
    novo = not log.exists() or args.forcar
    with open(log, "a" if not novo else "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos, delimiter=";")
        if novo:
            w.writeheader()
        w.writerows(linhas)

    dt = time.perf_counter() - t0
    tot_pag = sum(r["paginas"] for r in linhas)
    tot_ocr = sum(r["pags_ocr"] for r in linhas)
    erros = sum(1 for r in linhas if r["status"] == "erro")
    print(f"\nConcluído em {dt/60:.1f} min: {len(linhas)} arquivo(s), {tot_pag} páginas "
          f"({tot_ocr} por OCR), {erros} erro(s).")
    print(f"Texto em {saida}/  |  log em {log}")


if __name__ == "__main__":
    main()
