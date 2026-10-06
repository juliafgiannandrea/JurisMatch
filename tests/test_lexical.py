from jurismatch.lexical import IndiceLexical, tokenizar


def test_tokenizar_remove_stopwords_e_aplica_stemmer():
    assert tokenizar(["a recuperação judicial das empresas"]) == [["recuper", "judicial", "empres"]]


def test_pontuar_e_persistir(tmp_path):
    textos = ["lei de falências e recuperação judicial", "liberdade de imprensa", "tributo estadual"]
    indice = IndiceLexical.construir(textos)
    scores = indice.pontuar("recuperação judicial de empresas")
    assert scores.shape == (3,)
    assert scores.argmax() == 0 and scores[1] == 0 and scores[2] == 0
    indice.salvar(tmp_path / "bm25")
    recarregado = IndiceLexical.carregar(tmp_path / "bm25")
    assert recarregado.pontuar("imprensa").argmax() == 1
