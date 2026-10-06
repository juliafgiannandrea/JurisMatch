import hashlib

import numpy as np
import pandas as pd
import pytest

from jurismatch.chunking import gerar_chunks
from jurismatch.limpeza import Bloco


class EmbedderFalso:
    """Embedder determinístico para testes: saco de palavras projetado em 64 dimensões."""

    nome_modelo = "falso-64d"

    def _vetor(self, texto: str) -> np.ndarray:
        v = np.zeros(64, dtype="float32")
        for palavra in texto.lower().split():
            v[int(hashlib.md5(palavra.strip(".,;:").encode()).hexdigest(), 16) % 64] += 1.0
        norma = np.linalg.norm(v)
        return v / norma if norma else v

    def codificar_passagens(self, textos):
        return np.stack([self._vetor(t) for t in textos])

    def codificar_consulta(self, consulta):
        return self._vetor(consulta)


TEXTOS = {
    ("ADI", 1): [
        "A liberdade de imprensa protege as empresas jornalísticas contra a censura prévia.",
        "Pede-se a procedência da ação para declarar a inconstitucionalidade da norma.",
    ],
    ("ADI", 2): [
        "O imposto estadual sobre circulação de mercadorias viola a legalidade tributária.",
        "Pede-se a procedência da ação para declarar a inconstitucionalidade da norma.",
    ],
    ("ADC", 3): [
        "A recuperação judicial e a falência seguem a Lei 11.101/2005, cuja validade se afirma.",
    ],
}


@pytest.fixture
def embedder_falso():
    return EmbedderFalso()


@pytest.fixture
def chunks_exemplo():
    linhas = []
    for (classe, numero), paragrafos in TEXTOS.items():
        blocos = [Bloco(p, "paragrafo", i + 1, i + 1, frozenset({"nativo"})) for i, p in enumerate(paragrafos)]
        novos, _ = gerar_chunks(
            blocos, doc_id=f"{classe}_{numero}", classe=classe, numero=numero,
            arquivo_pdf=f"{classe}_{numero}_peticao_inicial.pdf",
            contar_tokens=lambda t: len(t.split()), alvo=5, teto=60,
        )
        linhas.extend(novos)
    return pd.DataFrame(linhas)
