"""Converte uma planilha de processos (classe + número) para o formato do baixar_peticoes_stf.py.

O download precisa das colunas "Processo" (ex.: "ADI 6115") e "Link do processo"
(portal.stf.jus.br/processos/detalhe.asp?incidente=N). Quando a planilha de entrada só tem
classe e número, o incidente é procurado:
  1. na planilha base do STF (base_inicial_...xlsx), que já tem o link;
  2. no portal: listarProcessos.asp?classe=X&numeroProcesso=N redireciona para detalhe.asp?incidente=N.
     Essa página não fica atrás do WAF, então basta um GET sem seguir o redirecionamento.

Uso:
    python preparar_planilha.py "../../casos_para_teste (1).xlsx" -o casos_mp.xlsx
    python preparar_planilha.py entrada.xlsx --col-classe SIG_CLASSE_PROCES --col-numero NUM_PROCESSO
"""
from __future__ import annotations

import argparse
import random
import re
import time
from pathlib import Path

import pandas as pd
import requests

PASTA = Path(__file__).resolve().parent
PLANILHA_BASE = PASTA / "base_inicial_controle_concentrado_stf_2026_09_08.xlsx"
URL_BUSCA = "https://portal.stf.jus.br/processos/listarProcessos.asp?classe={classe}&numeroProcesso={numero}"
URL_DETALHE = "https://portal.stf.jus.br/processos/detalhe.asp?incidente={inc}"
RE_INCIDENTE = re.compile(r"incidente=(\d+)")


def incidentes_conhecidos() -> dict[str, str]:
    """'ADI 6115' -> incidente, a partir da planilha base do STF."""
    if not PLANILHA_BASE.exists():
        return {}
    base = pd.read_excel(PLANILHA_BASE, usecols=["Processo", "Link do processo"])
    achados = base["Link do processo"].astype(str).str.extract(RE_INCIDENTE)[0]
    return dict(zip(base["Processo"].str.strip(), achados.dropna()))


def buscar_incidente(sessao: requests.Session, classe: str, numero: int, tentativas: int = 3) -> str | None:
    url = URL_BUSCA.format(classe=classe, numero=numero)
    for tentativa in range(tentativas):
        try:
            r = sessao.get(url, allow_redirects=False, timeout=30)
            m = RE_INCIDENTE.search(r.headers.get("Location", ""))
            if m:
                return m.group(1)
            if r.status_code == 200:  # sem redirecionamento: processo não encontrado
                return None
        except requests.RequestException:
            pass
        time.sleep(2 * (tentativa + 1))
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path)
    ap.add_argument("-o", "--saida", type=Path, default=PASTA / "casos_preparados.xlsx")
    ap.add_argument("--col-classe", default="SIG_CLASSE_PROCES")
    ap.add_argument("--col-numero", default="NUM_PROCESSO")
    args = ap.parse_args()

    df = pd.read_excel(args.entrada)
    df["Processo"] = df[args.col_classe].str.strip() + " " + df[args.col_numero].astype(int).astype(str)
    df = df.drop_duplicates("Processo").reset_index(drop=True)

    conhecidos = incidentes_conhecidos()
    df["incidente"] = df["Processo"].map(conhecidos)
    faltam = df["incidente"].isna()
    print(f"{len(df)} processos; {(~faltam).sum()} com incidente na planilha base; {faltam.sum()} a buscar no portal")

    sessao = requests.Session()
    sessao.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64)"
    for i, idx in enumerate(df.index[faltam], start=1):
        linha = df.loc[idx]
        df.loc[idx, "incidente"] = buscar_incidente(sessao, linha[args.col_classe].strip(), int(linha[args.col_numero]))
        if i % 25 == 0:
            print(f"  {i}/{faltam.sum()} buscados")
        time.sleep(random.uniform(0.5, 1.2))

    sem = df["incidente"].isna()
    df["Link do processo"] = df["incidente"].map(lambda inc: URL_DETALHE.format(inc=inc) if pd.notna(inc) else None)
    df[~sem].drop(columns="incidente").to_excel(args.saida, index=False)
    print(f"{(~sem).sum()} processos gravados em {args.saida}")
    if sem.any():
        print(f"ATENÇÃO: {sem.sum()} sem incidente (não encontrados no portal): {', '.join(df.loc[sem, 'Processo'])}")


if __name__ == "__main__":
    main()
