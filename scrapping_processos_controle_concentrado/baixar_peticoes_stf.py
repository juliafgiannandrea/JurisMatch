"""
Baixa as petições iniciais de processos do STF a partir da planilha.

Fluxo real do site (verificado no navegador):
  1. Link da planilha:  portal.stf.jus.br/processos/detalhe.asp?incidente=N
  2. Botão "Peças" abre: redir.stf.jus.br/estfvisualizadorpub/jsp/consultarprocessoeletronico/
                         ConsultarProcessoEletronico.jsf?seqobjetoincidente=N
  3. Nessa página o link "Petição inicial" aponta para
     redir.stf.jus.br/paginadorpub/paginador.jsp?docTP=TP&docID=X&prcID=N
     e essa URL devolve o PDF diretamente (Content-Type: application/pdf).

Bloqueio: o redir.stf.jus.br está atrás do AWS WAF com ação "challenge".
Sem o cookie aws-waf-token a resposta é HTTP 202 vazio. O desafio é em JavaScript
(não é captcha), então um Chromium real via Playwright resolve sozinho. O script
usa o navegador para obter o token e faz os downloads pela mesma sessão
(context.request compartilha os cookies). Se o token expirar (202 de novo),
ele recarrega a página no navegador e tenta de novo.

Instalação (uma vez):
    pip install pandas openpyxl playwright
    playwright install chromium

Uso:
    python baixar_peticoes_stf.py
    (ou ajuste as variáveis em CONFIGURAÇÃO abaixo / use os argumentos de linha de comando)
"""

import argparse
import csv
import hashlib
import html
import random
import re
import time
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ============================ CONFIGURAÇÃO ============================
QUANTIDADE_PETICOES = 60          # <-- quantas petições (linhas da planilha) baixar
PLANILHA = "base_inicial_controle_concentrado_stf_2026_09_08.xlsx"       # planilha de entrada
COLUNA_LINK = "Link do processo"     # coluna com o link do processo
COLUNA_NOME = "Processo"          # coluna usada para nomear o PDF (ex.: "ADC 3")
PASTA_SAIDA = "peticoes_processos_estruturantes" # pasta onde os PDFs serão salvos
LINHA_INICIAL = 0                 # pular as N primeiras linhas (0 = começar do início)
HEADLESS = False                  # False = janela visível (mais confiável contra o WAF)
PAUSA_MIN, PAUSA_MAX = 1.5, 4.0   # pausa aleatória (segundos) entre processos
PULAR_JA_BAIXADOS = True          # não baixar de novo o que já existe na pasta
# ======================================================================

URL_PECAS = ("https://redir.stf.jus.br/estfvisualizadorpub/jsp/"
             "consultarprocessoeletronico/ConsultarProcessoEletronico.jsf?seqobjetoincidente={inc}")
RE_INCIDENTE = re.compile(r"incidente=(\d+)")
# o tipo da peça vem ANTES do " - " (ex.: "Petição inicial - Petição Inicial 1"); ancorar no início evita
# pegar "Documento comprobatório - ... Petição Inicial" ou "Comunicação ... Petição Inicial"
RE_PETICAO = re.compile(r"^\s*peti[cç][aã]o\s+inicial\b", re.IGNORECASE)
RE_ANCHOR = re.compile(r'<a\s[^>]*href="([^"]*paginador\.jsp[^"]*)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
MSG_SEM_PECA = "Ausência de peça eletrônica"


def nome_seguro(texto: str) -> str:
    return re.sub(r"[^\w\-]+", "_", str(texto)).strip("_")


def extrair_links_peticao(html_pagina: str, incidente: str):
    """Retorna lista de (rotulo, url) das peças 'Petição inicial', sem duplicatas de docID."""
    vistos, resultado = set(), []
    for href, rotulo_html in RE_ANCHOR.findall(html_pagina):
        rotulo = html.unescape(re.sub(r"<[^>]+>", "", rotulo_html)).strip()
        if not RE_PETICAO.search(rotulo):
            continue
        href = html.unescape(href).split("#")[0]
        doc_id = (re.search(r"docID=(\d+)", href) or [None, None])[1]
        if doc_id in vistos:
            continue
        vistos.add(doc_id)
        # garante que o prcID seja o do incidente da planilha
        href = re.sub(r"prcID=\d+", f"prcID={incidente}", href)
        resultado.append((rotulo, href))
    return resultado


def passou_no_desafio(pagina) -> bool:
    """True quando a página de peças carregou de verdade (e não a interstitial do WAF)."""
    conteudo = pagina.content()
    return ("paginador.jsp" in conteudo) or (MSG_SEM_PECA in conteudo) or ("Processo (" in conteudo)


def abrir_pagina_pecas(pagina, incidente: str, tentativas: int = 3) -> str:
    """Abre a página de peças no navegador (resolve o desafio do WAF) e devolve o HTML."""
    url = URL_PECAS.format(inc=incidente)
    for t in range(1, tentativas + 1):
        pagina.goto(url, wait_until="domcontentloaded", timeout=60_000)
        # o WAF pode mostrar uma interstitial e recarregar sozinho; espera até 30 s
        limite = time.time() + 30
        while time.time() < limite:
            if passou_no_desafio(pagina):
                return pagina.content()
            pagina.wait_for_timeout(1000)
        print(f"    [aviso] desafio do WAF não resolvido (tentativa {t}/{tentativas}); tentando de novo...")
        pagina.wait_for_timeout(3000)
    raise RuntimeError("não foi possível passar pelo desafio do WAF")


def baixar_pdf(contexto, pagina, url: str, destino: Path, incidente: str, tentativas: int = 3) -> int:
    """Baixa o PDF usando a sessão do navegador. Devolve o tamanho em bytes."""
    for t in range(1, tentativas + 1):
        resp = contexto.request.get(url, headers={"Referer": URL_PECAS.format(inc=incidente)}, timeout=120_000)
        corpo = resp.body()
        if resp.status == 200 and corpo[:5] == b"%PDF-":
            destino.write_bytes(corpo)
            return len(corpo)
        acao = resp.headers.get("x-amzn-waf-action", "")
        print(f"    [aviso] resposta {resp.status} {acao} ({len(corpo)} bytes) na tentativa {t}/{tentativas}; renovando token...")
        # renova o token do WAF recarregando a página no navegador
        abrir_pagina_pecas(pagina, incidente)
        pagina.wait_for_timeout(2000)
    raise RuntimeError(f"PDF não obtido: {url}")


def main():
    ap = argparse.ArgumentParser(description="Baixa petições iniciais do STF a partir da planilha.")
    ap.add_argument("-n", "--quantidade", type=int, default=QUANTIDADE_PETICOES, help="quantidade de petições a baixar")
    ap.add_argument("-p", "--planilha", default=PLANILHA)
    ap.add_argument("-o", "--saida", default=PASTA_SAIDA)
    ap.add_argument("--inicio", type=int, default=LINHA_INICIAL, help="índice da primeira linha (0 = primeira)")
    ap.add_argument("--headless", action="store_true", default=HEADLESS, help="rodar sem janela do navegador")
    args = ap.parse_args()

    df = pd.read_excel(args.planilha)
    df = df.iloc[args.inicio: args.inicio + args.quantidade].copy()
    df["incidente"] = df[COLUNA_LINK].astype(str).str.extract(RE_INCIDENTE.pattern)[0]

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    log_path = saida / "log_download.csv"
    perfil = Path(".perfil_chromium_stf")  # perfil persistente: guarda o cookie do WAF entre execuções

    print(f"Baixando {len(df)} petição(ões) para '{saida}/' ...\n")

    linhas_log = []
    with sync_playwright() as pw:
        contexto = pw.chromium.launch_persistent_context(
            str(perfil),
            headless=args.headless,
            viewport={"width": 1280, "height": 800},
            locale="pt-BR",
            args=["--disable-blink-features=AutomationControlled"],
            # a cadeia de certificados do redir.stf.jus.br vem incompleta; o Chromium tolera, mas o
            # cliente HTTP do Playwright (Node) não -> "unable to verify the first certificate"
            ignore_https_errors=True,
        )
        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()

        for i, (_, linha) in enumerate(df.iterrows(), start=1):
            processo = str(linha[COLUNA_NOME])
            incidente = linha["incidente"]
            prefixo = f"[{i}/{len(df)}] {processo} (incidente {incidente})"
            registro = {"processo": processo, "incidente": incidente, "status": "", "arquivos": "", "obs": ""}

            if pd.isna(incidente):
                print(f"{prefixo}: link sem incidente, pulando.")
                registro.update(status="erro", obs="link sem incidente")
                linhas_log.append(registro)
                continue

            base = nome_seguro(processo) or f"inc_{incidente}"
            if PULAR_JA_BAIXADOS and list(saida.glob(f"{base}_peticao_inicial*.pdf")):
                print(f"{prefixo}: já baixado, pulando.")
                registro.update(status="ja_existia")
                linhas_log.append(registro)
                continue

            try:
                html_pecas = abrir_pagina_pecas(pagina, incidente)
                links = extrair_links_peticao(html_pecas, incidente)

                if not links:
                    obs = "sem peça eletrônica / visualização restrita" if MSG_SEM_PECA in html_pecas \
                          else "nenhum link 'Petição inicial' encontrado"
                    print(f"{prefixo}: {obs}.")
                    registro.update(status="sem_peticao", obs=obs)
                    linhas_log.append(registro)
                    continue

                arquivos, hashes = [], set()
                for k, (rotulo, url) in enumerate(links, start=1):
                    sufixo = "" if len(links) == 1 else f"_parte{k:02d}"
                    destino = saida / f"{base}_peticao_inicial{sufixo}.pdf"
                    tamanho = baixar_pdf(contexto, pagina, url, destino, incidente)
                    # o STF às vezes registra o MESMO arquivo em docIDs diferentes: descarta cópias idênticas
                    h = hashlib.md5(destino.read_bytes()).hexdigest()
                    if h in hashes:
                        destino.unlink()
                        print(f"{prefixo}: {rotulo} é cópia idêntica de outra parte, descartada")
                        continue
                    hashes.add(h)
                    arquivos.append(destino.name)
                    print(f"{prefixo}: {rotulo} -> {destino.name} ({tamanho/1024:.0f} KB)")
                    time.sleep(random.uniform(0.5, 1.5))
                # se sobrou só um arquivo com sufixo _parte01, renomeia para o nome simples
                if len(arquivos) == 1 and arquivos[0].endswith("_parte01.pdf"):
                    novo = saida / f"{base}_peticao_inicial.pdf"
                    (saida / arquivos[0]).rename(novo)
                    arquivos = [novo.name]

                registro.update(status="ok", arquivos=";".join(arquivos))
            except (PWTimeout, RuntimeError, Exception) as e:  # noqa: BLE001
                print(f"{prefixo}: ERRO - {e}")
                registro.update(status="erro", obs=str(e)[:200])

            linhas_log.append(registro)
            time.sleep(random.uniform(PAUSA_MIN, PAUSA_MAX))

        contexto.close()

    with open(log_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["processo", "incidente", "status", "arquivos", "obs"], delimiter=";")
        w.writeheader()
        w.writerows(linhas_log)

    ok = sum(1 for r in linhas_log if r["status"] == "ok")
    print(f"\nConcluído: {ok} baixado(s), "
          f"{sum(1 for r in linhas_log if r['status']=='sem_peticao')} sem petição, "
          f"{sum(1 for r in linhas_log if r['status']=='erro')} erro(s). Log em {log_path}")


if __name__ == "__main__":
    main()
