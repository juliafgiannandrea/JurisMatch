import json

import pytest

from jurismatch import config
from jurismatch.busca import modelo_do_indice


@pytest.mark.parametrize(
    "modelo, consulta, passagem",
    [
        ("intfloat/multilingual-e5-base", "query: ", "passage: "),
        ("intfloat/multilingual-e5-large", "query: ", "passage: "),
        ("Qwen/Qwen3-Embedding-0.6B", f"Instruct: {config.INSTRUCAO_BUSCA}\nQuery:", ""),
        ("intfloat/multilingual-e5-large-instruct", f"Instruct: {config.INSTRUCAO_BUSCA}\nQuery: ", ""),
        ("BAAI/bge-m3", "", ""),
    ],
)
def test_prefixos_por_modelo(modelo, consulta, passagem):
    assert config.prefixos(modelo) == (consulta, passagem)


def test_modelo_do_indice_le_o_manifesto(tmp_path):
    (tmp_path / "manifesto.json").write_text(json.dumps({"modelo": "Qwen/Qwen3-Embedding-0.6B"}))
    assert modelo_do_indice(tmp_path) == "Qwen/Qwen3-Embedding-0.6B"


def test_modelo_do_indice_sem_manifesto_usa_o_padrao(tmp_path):
    assert modelo_do_indice(tmp_path) == config.MODELO_EMBEDDING
