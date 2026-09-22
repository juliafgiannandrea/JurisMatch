"""
Calcula métricas de qualidade de uma extração de texto de petições do STF.

Feito para BENCHMARK: pontua qualquer pasta de .txt, venha ela deste projeto ou
da solução de outra pessoa. Basta que cada PDF de entrada vire um .txt de mesmo
nome base. Assim todas as soluções são medidas pelo mesmo critério, sobre o
mesmo conjunto de documentos.

    python metricas_extracao.py \
        --solucao minha=../extracao_texto_peticoes/texto_peticoes \
        --solucao colega_a=/caminho/da/saida_dele \
        --pdfs ../scrapping_processos_controle_concentrado/peticoes_processos_estruturantes

O que é medido, e por quê:

  1. COBERTURA — quanto do material de entrada virou texto.
     Uma solução pode parecer ótima em qualidade simplesmente por ter descartado
     as páginas difíceis. Cobertura e qualidade têm que ser lidas juntas.

  2. QUALIDADE LÉXICA — proxy de acurácia sem precisar de gabarito.
     Mede a fração de palavras que existem no dicionário pt_BR do sistema.
     Texto nativo fica alto; OCR ruim derruba esse número. É o indicador mais
     sensível a erro de reconhecimento.

  3. RUÍDO — frequência de tokens impossíveis em português (sem vogal, mistura
     de letra e dígito, símbolos soltos). Sobe quando o OCR alucina.

  4. ESTRUTURA JURÍDICA — recall de conteúdo que quase toda petição inicial tem
     (endereçamento ao STF, citação de artigo, citação de lei). Detecta extração
     que rodou sem erro mas perdeu o corpo do documento.

  5. DESEMPENHO — lido do log de extração, se informado.

ATENÇÃO: nenhuma destas métricas é acurácia de verdade, porque não há gabarito.
Para erro de caractere e de palavra medidos contra referência real, use o outro
script, benchmark_ocr.py, que constrói gabarito a partir das páginas nativas.

Instalação:
    pip install pymupdf          # só para contar páginas dos PDFs
"""

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

# ============================ CONFIGURAÇÃO ============================
DICIONARIOS = [                      # primeiro que existir é usado
    "/usr/share/dict/brazilian",
    "/usr/share/dict/portuguese",
]
MIN_TAMANHO_TOKEN = 3                # tokens menores não entram na taxa de dicionário
RE_MARCADOR = re.compile(r"^\[\[pagina (\d+) \| (\w+)\]\]$", re.MULTILINE)
# "palavra" = sequência de letras, aceitando hífen e apóstrofo internos
RE_TOKEN = re.compile(r"[^\W\d_]+(?:[-'][^\W\d_]+)*", re.UNICODE)

# âncoras que uma petição inicial de controle concentrado praticamente sempre tem
ANCORAS = {
    "enderecamento": re.compile(r"excelent[íi]ssim|supremo\s+tribunal\s+federal", re.I),
    "cita_artigo": re.compile(r"\bart(?:igo|\.)\s*\d+", re.I),
    "cita_lei": re.compile(r"\blei\s+(?:federal\s+)?n[ºo°\.]", re.I),
    "constituicao": re.compile(r"constitui[çc][ãa]o|constitucional", re.I),
    "pedido": re.compile(r"\b(?:requer|pede|pugna|postula)\b", re.I),
}
# ======================================================================


# ------------------------------------------------------------- utilidades

def carregar_dicionario(caminhos):
    for c in caminhos:
        p = Path(c)
        if p.is_file():
            palavras = set()
            with open(p, encoding="utf-8", errors="ignore") as f:
                for linha in f:
                    w = linha.strip()
                    if w:
                        palavras.add(w.lower())
                        palavras.add(sem_acento(w.lower()))
            return palavras, str(p)
    return set(), ""


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def eh_lixo(token: str) -> bool:
    """Token que não pode ser uma palavra em português."""
    t = token.lower()
    if len(t) >= 3 and not re.search(r"[aeiouáàâãéêíóôõúü]", t):
        return True                                   # sem nenhuma vogal
    if re.search(r"(.)\1{3,}", t):
        return True                                   # 4+ letras iguais seguidas
    return False


def ler_texto(caminho: Path):
    """Devolve (texto_sem_marcadores, [(metodo, texto_da_pagina), ...]).

    A lista por página só vem preenchida quando a solução grava os marcadores.
    É ela que permite separar a qualidade do texto nativo da do texto de OCR,
    que é o número que de fato mede o reconhecimento.
    """
    bruto = caminho.read_text(encoding="utf-8", errors="replace")
    pedacos = RE_MARCADOR.split(bruto)          # [antes, n, metodo, texto, n, metodo, texto, ...]
    if len(pedacos) == 1:
        return bruto, []
    paginas = []
    for i in range(1, len(pedacos) - 2, 3):
        paginas.append((pedacos[i + 1], pedacos[i + 2]))
    return pedacos[0] + "".join(t for _, t in paginas), paginas


# --------------------------------------------------------------- métricas

def medir_solucao(nome, pasta_txt, paginas_por_pdf, dicionario):
    pasta = Path(pasta_txt)
    txts = sorted(p for p in pasta.glob("*.txt"))
    esperados = set(paginas_por_pdf) if paginas_por_pdf else set()

    r = {"solucao": nome, "arquivos_txt": len(txts)}
    total_chars = total_tokens = tokens_lixo = tokens_1char = soma_tam = 0
    # contadores por método de extração: permitem isolar a qualidade do OCR
    dic_ok = Counter()          # método -> tokens encontrados no dicionário
    dic_eleg = Counter()        # método -> tokens elegíveis (tamanho mínimo)
    lixo_por_metodo = Counter()
    tok_por_metodo = Counter()
    metodos = Counter()
    docs_com_ancora = Counter()
    paginas_marcadas = 0
    vazios = []
    nomes_txt = set()

    def contar(tokens, metodo):
        nonlocal total_tokens, tokens_lixo, tokens_1char, soma_tam
        for tok in tokens:
            total_tokens += 1
            soma_tam += len(tok)
            tok_por_metodo[metodo] += 1
            if len(tok) == 1:
                tokens_1char += 1
            if eh_lixo(tok):
                tokens_lixo += 1
                lixo_por_metodo[metodo] += 1
            # denominador da taxa de dicionário: só tokens com tamanho mínimo
            if len(tok) >= MIN_TAMANHO_TOKEN:
                dic_eleg[metodo] += 1
                if dicionario:
                    tl = tok.lower()
                    if tl in dicionario or sem_acento(tl) in dicionario:
                        dic_ok[metodo] += 1

    for t in txts:
        texto, paginas = ler_texto(t)
        nomes_txt.add(t.stem)
        metodos.update(m for m, _ in paginas)
        paginas_marcadas += len(paginas)
        chars = len(re.sub(r"\s", "", texto))
        total_chars += chars
        if chars < 200:
            vazios.append(t.stem)

        if paginas:
            for metodo, txt_pag in paginas:
                contar(RE_TOKEN.findall(txt_pag), metodo)
        else:
            contar(RE_TOKEN.findall(texto), "total")   # solução sem marcadores

        for chave, rx in ANCORAS.items():
            if rx.search(texto):
                docs_com_ancora[chave] += 1

    tokens_dic = sum(dic_ok.values())
    tokens_elegiveis = sum(dic_eleg.values())
    n = max(len(txts), 1)
    r["chars_total"] = total_chars
    r["chars_por_arquivo"] = round(total_chars / n)
    r["tokens_total"] = total_tokens
    r["tam_medio_token"] = round(soma_tam / max(total_tokens, 1), 2)
    r["taxa_dicionario"] = round(tokens_dic / max(tokens_elegiveis, 1), 4) if dicionario else None
    r["taxa_lixo"] = round(tokens_lixo / max(total_tokens, 1), 4)
    r["taxa_token_1char"] = round(tokens_1char / max(total_tokens, 1), 4)
    r["arquivos_quase_vazios"] = len(vazios)

    # o número que realmente mede o OCR: qualidade léxica separada por origem.
    # o texto nativo é o teto alcançável neste corpus; a diferença é o custo do OCR.
    for metodo in ("nativo", "ocr"):
        eleg, tot = dic_eleg.get(metodo, 0), tok_por_metodo.get(metodo, 0)
        r[f"dicionario_{metodo}"] = round(dic_ok.get(metodo, 0) / eleg, 4) if eleg and dicionario else None
        r[f"lixo_{metodo}"] = round(lixo_por_metodo.get(metodo, 0) / tot, 4) if tot else None
    if r.get("dicionario_nativo") is not None and r.get("dicionario_ocr") is not None:
        r["defasagem_ocr"] = round(r["dicionario_nativo"] - r["dicionario_ocr"], 4)
    else:
        r["defasagem_ocr"] = None

    # cobertura contra os PDFs de entrada
    if esperados:
        faltando = esperados - nomes_txt
        r["pdfs_entrada"] = len(esperados)
        r["arquivos_faltando"] = len(faltando)
        r["cobertura_arquivos"] = round(len(nomes_txt & esperados) / len(esperados), 4)
        pag_tot = sum(paginas_por_pdf.values())
        pag_cob = sum(v for k, v in paginas_por_pdf.items() if k in nomes_txt)
        r["paginas_entrada"] = pag_tot
        r["cobertura_paginas"] = round(pag_cob / max(pag_tot, 1), 4)
        r["chars_por_pagina"] = round(total_chars / max(pag_cob, 1))
    else:
        r["pdfs_entrada"] = r["arquivos_faltando"] = None
        r["cobertura_arquivos"] = r["cobertura_paginas"] = r["chars_por_pagina"] = None

    # composição, só se a solução gravar marcadores (a nossa grava)
    if paginas_marcadas:
        for m in ("nativo", "ocr", "vazia", "ocr_falhou", "pendente"):
            r[f"pags_{m}"] = metodos.get(m, 0)
        r["fracao_ocr"] = round(metodos.get("ocr", 0) / max(paginas_marcadas, 1), 4)
    else:
        for m in ("nativo", "ocr", "vazia", "ocr_falhou", "pendente"):
            r[f"pags_{m}"] = None
        r["fracao_ocr"] = None

    for chave in ANCORAS:
        r[f"ancora_{chave}"] = round(docs_com_ancora[chave] / n, 4)

    r["_vazios"] = vazios
    return r


def contar_paginas(pasta_pdfs):
    """Mapa nome_base -> nº de páginas. Precisa do PyMuPDF."""
    if not pasta_pdfs:
        return {}
    try:
        import pymupdf
    except ImportError:
        print("[aviso] PyMuPDF não instalado; métricas de cobertura serão puladas.", file=sys.stderr)
        return {}
    mapa = {}
    for pdf in sorted(Path(pasta_pdfs).glob("*.pdf")):
        try:
            d = pymupdf.open(pdf)
            mapa[pdf.stem] = d.page_count
            d.close()
        except Exception as e:  # noqa: BLE001
            print(f"[aviso] não abriu {pdf.name}: {e}", file=sys.stderr)
    return mapa


def ler_log(caminho):
    """Extrai desempenho do log_extracao.csv, se existir."""
    p = Path(caminho) if caminho else None
    if not p or not p.is_file():
        return {}
    seg = pag = 0.0
    try:
        with open(p, encoding="utf-8-sig", newline="") as f:
            for linha in csv.DictReader(f, delimiter=";"):
                seg += float(linha.get("segundos") or 0)
                pag += float(linha.get("paginas") or 0)
    except Exception:
        return {}
    if not pag:
        return {}
    return {"segundos_cpu": round(seg, 1), "seg_por_pagina": round(seg / pag, 3)}


# ------------------------------------------------------------------ saída

def imprimir(resultados, dic_usado):
    LINHAS = [
        ("COBERTURA", None),
        ("  PDFs de entrada", "pdfs_entrada"),
        ("  arquivos .txt gerados", "arquivos_txt"),
        ("  arquivos faltando", "arquivos_faltando"),
        ("  cobertura de arquivos", "cobertura_arquivos"),
        ("  cobertura de páginas", "cobertura_paginas"),
        ("  arquivos quase vazios", "arquivos_quase_vazios"),
        ("VOLUME", None),
        ("  caracteres no total", "chars_total"),
        ("  caracteres por página", "chars_por_pagina"),
        ("  tamanho médio do token", "tam_medio_token"),
        ("QUALIDADE LÉXICA", None),
        ("  taxa de dicionário (geral)", "taxa_dicionario"),
        ("  taxa de ruído (geral)", "taxa_lixo"),
        ("  taxa de token de 1 char", "taxa_token_1char"),
        ("QUALIDADE POR ORIGEM DO TEXTO", None),
        ("  dicionário, páginas nativas", "dicionario_nativo"),
        ("  dicionário, páginas de OCR", "dicionario_ocr"),
        ("  ruído, páginas nativas", "lixo_nativo"),
        ("  ruído, páginas de OCR", "lixo_ocr"),
        ("  defasagem do OCR", "defasagem_ocr"),
        ("COMPOSIÇÃO", None),
        ("  páginas nativas", "pags_nativo"),
        ("  páginas por OCR", "pags_ocr"),
        ("  páginas vazias", "pags_vazia"),
        ("  falhas de OCR", "pags_ocr_falhou"),
        ("  fração vinda de OCR", "fracao_ocr"),
        ("ESTRUTURA JURÍDICA (fração dos documentos)", None),
        ("  endereçamento ao STF", "ancora_enderecamento"),
        ("  cita artigo", "ancora_cita_artigo"),
        ("  cita lei", "ancora_cita_lei"),
        ("  menciona Constituição", "ancora_constituicao"),
        ("  formula pedido", "ancora_pedido"),
        ("DESEMPENHO", None),
        ("  segundos de CPU", "segundos_cpu"),
        ("  segundos por página", "seg_por_pagina"),
    ]
    nomes = [r["solucao"] for r in resultados]
    larg = max(44, max((len(n) for n in nomes), default=10) + 2)
    print("\n" + "=" * (larg + 18 * len(nomes)))
    print("MÉTRICAS DE EXTRAÇÃO")
    if dic_usado:
        print(f"dicionário: {dic_usado}")
    print("=" * (larg + 18 * len(nomes)))
    print(f"{'':{larg}}" + "".join(f"{n:>18}" for n in nomes))
    for rotulo, chave in LINHAS:
        if chave is None:
            print(f"\n{rotulo}")
            continue
        celulas = []
        for r in resultados:
            v = r.get(chave)
            if v is None:
                celulas.append(f"{'-':>18}")
            elif isinstance(v, float):
                celulas.append(
                    f"{v:>18.2%}" if chave.startswith(("taxa", "cobertura", "fracao", "ancora",
                                                       "dicionario_", "lixo_", "defasagem"))
                    else f"{v:>18.2f}")
            else:
                celulas.append(f"{v:>18,}".replace(",", "."))
        print(f"{rotulo:{larg}}" + "".join(celulas))
    print()
    for r in resultados:
        if r["_vazios"]:
            print(f"[{r['solucao']}] arquivos quase vazios: {', '.join(r['_vazios'][:8])}"
                  + (" ..." if len(r["_vazios"]) > 8 else ""))


def main():
    ap = argparse.ArgumentParser(
        description="Métricas comparáveis de extração de texto (para benchmark entre soluções).")
    ap.add_argument("--solucao", action="append", required=True, metavar="NOME=PASTA",
                    help="pasta de .txt a avaliar; repita o argumento para comparar soluções")
    ap.add_argument("--pdfs", default=None, help="pasta dos PDFs de entrada (para medir cobertura)")
    ap.add_argument("--log", default=None, help="log_extracao.csv para as métricas de desempenho")
    ap.add_argument("--dicionario", default=None, help="lista de palavras alternativa")
    ap.add_argument("--csv", default="metricas_extracao.csv", help="arquivo CSV de saída")
    ap.add_argument("--json", default=None, help="também grava o resultado bruto em JSON")
    args = ap.parse_args()

    caminhos = [args.dicionario] if args.dicionario else DICIONARIOS
    dicionario, dic_usado = carregar_dicionario(caminhos)
    if not dicionario:
        print("[aviso] nenhum dicionário encontrado; taxa de dicionário será pulada.\n"
              "        instale com: sudo apt install wbrazilian", file=sys.stderr)

    paginas = contar_paginas(args.pdfs)
    desempenho = ler_log(args.log)

    resultados = []
    for spec in args.solucao:
        if "=" not in spec:
            sys.exit(f"ERRO: use NOME=PASTA, recebi '{spec}'")
        nome, pasta = spec.split("=", 1)
        if not Path(pasta).is_dir():
            sys.exit(f"ERRO: pasta não existe: {pasta}")
        r = medir_solucao(nome, pasta, paginas, dicionario)
        if len(args.solucao) == 1:
            r.update(desempenho)
        resultados.append(r)

    imprimir(resultados, dic_usado)

    campos = [k for k in resultados[0] if not k.startswith("_")]
    for r in resultados:
        for k in r:
            if not k.startswith("_") and k not in campos:
                campos.append(k)
    with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(resultados)
    print(f"\nCSV em {args.csv}")

    if args.json:
        Path(args.json).write_text(
            json.dumps([{k: v for k, v in r.items() if not k.startswith("_")} for r in resultados],
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON em {args.json}")


if __name__ == "__main__":
    main()
