"""Interface web do JurisMatch (Streamlit).

Uso, a partir da raiz do projeto:
    pip install -e ".[app]"
    streamlit run app/app.py

Precisa do índice em vectorstore/ (scripts/04_index.py).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # funciona mesmo sem pip install -e .

import streamlit as st

from jurismatch import config
from jurismatch.busca import Buscador, formatar_tempos

st.set_page_config(page_title="JurisMatch", page_icon="⚖️", layout="wide")


@st.cache_resource(show_spinner="Carregando o índice e os modelos…")
def carregar_buscador() -> Buscador:
    return Buscador(config.DIR_INDICE)


st.title("JurisMatch")
st.caption("Busca semântica em petições iniciais de ADI e ADC do STF")

with st.sidebar:
    st.header("Opções")
    k = st.slider("Petições no resultado (k)", 1, 100, 5)
    modo = st.selectbox("Modo", ["hibrido", "denso", "lexical"], format_func=lambda m: {
        "hibrido": "Híbrido (semântico + palavras)", "denso": "Só semântico", "lexical": "Só palavras (BM25)"
    }[m])
    classe = st.selectbox("Classe", ["Todas", "ADI", "ADC", "ADO", "ADPF"])
    rerank = st.toggle("Reranker (cross-encoder)", value=True, help="Mais preciso, porém ~40 s por consulta em CPU.")
    limiar = st.slider(
        "Relevância mínima", 0.5, 1.0, float(config.LIMIAR_RERANK), 0.05, disabled=not rerank,
        help="Petições cujo melhor trecho fica abaixo disso não aparecem.",
    )

consulta = st.text_input("Consulta", placeholder="ex.: liberdade de imprensa e capital estrangeiro")

if st.button("Buscar", type="primary", disabled=not consulta.strip()):
    buscador = carregar_buscador()
    with st.spinner("Buscando…"):
        resultados = buscador.buscar(
            consulta, k=k, modo=modo, classe=None if classe == "Todas" else classe, rerank=rerank, limiar=limiar
        )
    st.caption(formatar_tempos(buscador.ultimos_tempos))

    if not resultados:
        if rerank:
            st.warning(
                f"Nenhum resultado significativo: nenhuma petição atingiu relevância de {limiar:.0%}. "
                "Reformule a consulta ou reduza a relevância mínima."
            )
        else:
            st.warning("Nenhum resultado: nenhum trecho tem relação com a consulta.")

    for r in resultados:
        with st.container(border=True):
            cabeca, n1, n2 = st.columns([4, 1, 1])
            cabeca.subheader(f"{r['posicao']}. {r['classe']} {r['numero']}")
            if rerank:
                n1.metric("Relevância", f"{r['score']:.0%}")
            else:
                n1.metric("Score RRF", f"{r['score']:.4f}", help="Só ordena os resultados; não mede relevância.")
            if r["similaridade"] is not None:
                n2.metric("Similaridade", f"{r['similaridade']:.2f}", help="Cosseno entre a consulta e o trecho.")
            st.caption(f"{r['secao'] or 'sem seção'} · {r['arquivo_pdf']}, p. {r['pagina']} · extração {r['metodo_extracao']}")
            st.write(r["trecho"])
            pdf = config.DIR_PDF / r["arquivo_pdf"]
            if pdf.exists():
                st.download_button(
                    f"Baixar PDF (trecho na p. {r['pagina']})", pdf.read_bytes(), file_name=r["arquivo_pdf"],
                    mime="application/pdf", key=f"pdf_{r['chunk_id']}",
                )
