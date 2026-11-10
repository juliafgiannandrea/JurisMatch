import numpy as np
import pytest
from fastapi.testclient import TestClient

from jurismatch.api import criar_app
from jurismatch.busca import Buscador
from jurismatch.indexar import construir_indice


class RerankerFalso:
    """Nota 0.9 para trechos que contêm 'imprensa', 0.1 para os demais."""

    def pontuar(self, consulta, textos):
        return np.array([0.9 if "imprensa" in t else 0.1 for t in textos], dtype="float32")


@pytest.fixture
def dir_indice(tmp_path, chunks_exemplo, embedder_falso):
    destino = tmp_path / "vectorstore"
    destino.mkdir()
    construir_indice(chunks_exemplo, embedder_falso, destino)
    return destino


@pytest.fixture
def dir_pdf(tmp_path):
    pasta = tmp_path / "pdf"
    pasta.mkdir()
    (pasta / "ADI_1_peticao_inicial.pdf").write_bytes(b"%PDF-1.4 falso")
    (tmp_path / "segredo.pdf").write_bytes(b"%PDF-1.4 fora da pasta")
    return pasta


@pytest.fixture
def dir_web(tmp_path):
    pasta = tmp_path / "web"
    pasta.mkdir()
    (pasta / "index.html").write_text("<!doctype html><title>JurisMatch</title>", encoding="utf-8")
    (pasta / "sw.js").write_text("self.addEventListener('fetch', () => {});", encoding="utf-8")
    return pasta


@pytest.fixture
def arq_incidentes(tmp_path):
    arq = tmp_path / "log_download.csv"
    linhas = [
        "processo;incidente;status;arquivos;obs",
        "ADI 1;111222;ja_existia;;",
        "ADI 2;;falhou;;sem incidente",
        "ADO 9;abc;falhou;;nao numerico",
    ]
    arq.write_text(chr(10).join(linhas) + chr(10), encoding="utf-8-sig")
    return arq


@pytest.fixture
def cliente(dir_indice, dir_pdf, dir_web, embedder_falso, arq_incidentes):
    def fabrica():
        return Buscador(dir_indice, embedder=embedder_falso, reranker=RerankerFalso())

    return TestClient(
        criar_app(fabrica, dir_indice=dir_indice, dir_pdf=dir_pdf, dir_web=dir_web, arq_incidentes=arq_incidentes)
    )


@pytest.fixture
def cliente_sem_indice(tmp_path, dir_pdf, dir_web):
    def fabrica():
        raise AssertionError("não deve carregar o buscador sem índice")

    vazio = tmp_path / "sem_indice"
    return TestClient(criar_app(fabrica, dir_indice=vazio, dir_pdf=dir_pdf, dir_web=dir_web))


def test_status_com_indice(cliente):
    r = cliente.get("/api/status")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["indice_pronto"] is True
    assert corpo["buscador_carregado"] is False
    assert corpo["peticoes"] == 3
    assert corpo["trechos"] > 0
    assert corpo["modos"] == ["hibrido", "denso", "lexical"]
    assert corpo["classes"] == ["ADI", "ADC", "ADO", "ADPF"]
    assert corpo["limiar_padrao"] == 0.8
    assert corpo["modelo_embedding"] and corpo["modelo_reranker"]


def test_status_sem_indice(cliente_sem_indice):
    corpo = cliente_sem_indice.get("/api/status").json()
    assert corpo["indice_pronto"] is False
    assert corpo["peticoes"] is None and corpo["trechos"] is None


def test_status_nao_carrega_buscador_e_busca_marca_carregado(cliente):
    cliente.post("/api/buscar", json={"consulta": "liberdade de imprensa", "rerank": False})
    assert cliente.get("/api/status").json()["buscador_carregado"] is True


def test_buscar_ok(cliente):
    r = cliente.post(
        "/api/buscar",
        json={"consulta": "  liberdade de imprensa e censura ", "k": 3, "modo": "hibrido", "rerank": False},
    )
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["consulta"] == "liberdade de imprensa e censura"
    assert corpo["rerank"] is False
    assert isinstance(corpo["tempo_ms"], int)
    primeiro = corpo["resultados"][0]
    assert primeiro["doc_id"] == "ADI_1"
    assert primeiro["posicao"] == 1
    assert "link_pdf" not in primeiro
    assert primeiro["pdf_disponivel"] is True
    assert primeiro["url_pdf"] == "/api/pdf/ADI_1_peticao_inicial.pdf#page=1"
    assert isinstance(primeiro["similaridade"], float)


def test_buscar_url_stf(cliente):
    r = cliente.post("/api/buscar", json={"consulta": "imposto sobre liberdade de imprensa", "k": 10, "rerank": False})
    por_doc = {x["doc_id"]: x for x in r.json()["resultados"]}
    assert por_doc["ADI_1"]["url_stf"] == "https://portal.stf.jus.br/processos/detalhe.asp?incidente=111222"
    assert por_doc["ADI_2"]["url_stf"] is None  # linha sem incidente
    assert por_doc["ADC_3"]["url_stf"] is None  # fora do csv


def test_buscar_url_stf_nula_com_csv_ausente(dir_indice, dir_pdf, dir_web, embedder_falso, tmp_path):
    def fabrica():
        return Buscador(dir_indice, embedder=embedder_falso)

    c = TestClient(
        criar_app(fabrica, dir_indice=dir_indice, dir_pdf=dir_pdf, dir_web=dir_web, arq_incidentes=tmp_path / "nao.csv")
    )
    r = c.post("/api/buscar", json={"consulta": "liberdade de imprensa", "rerank": False})
    assert r.status_code == 200
    assert all(x["url_stf"] is None for x in r.json()["resultados"])


def test_buscar_pdf_indisponivel(cliente):
    r = cliente.post("/api/buscar", json={"consulta": "imposto sobre circulação de mercadorias", "k": 5, "rerank": False})
    adi2 = next(x for x in r.json()["resultados"] if x["doc_id"] == "ADI_2")
    assert adi2["pdf_disponivel"] is False
    assert adi2["url_pdf"] is None


def test_buscar_lexical_similaridade_nula_e_json_valido(cliente):
    r = cliente.post("/api/buscar", json={"consulta": "Lei 11.101/2005", "modo": "lexical", "rerank": False})
    assert r.status_code == 200
    assert r.json()["resultados"][0]["similaridade"] is None


def test_buscar_com_rerank_e_limiar(cliente):
    r = cliente.post(
        "/api/buscar", json={"consulta": "liberdade de imprensa", "rerank": True, "limiar": 0.6, "k": 10}
    )
    corpo = r.json()
    assert [x["doc_id"] for x in corpo["resultados"]] == ["ADI_1"]
    assert corpo["resultados"][0]["score"] == pytest.approx(0.9)
    assert corpo["rerank"] is True and corpo["limiar"] == 0.6


def test_buscar_com_filtro_de_classe(cliente):
    r = cliente.post(
        "/api/buscar",
        json={"consulta": "inconstitucionalidade da norma e validade da falência", "classe": "ADC", "rerank": False},
    )
    assert {x["classe"] for x in r.json()["resultados"]} == {"ADC"}


@pytest.mark.parametrize(
    "corpo",
    [
        {},
        {"consulta": ""},
        {"consulta": "   "},
        {"consulta": "x" * 501},
        {"consulta": "ok", "k": 0},
        {"consulta": "ok", "k": 21},
        {"consulta": "ok", "modo": "magico"},
        {"consulta": "ok", "classe": "RE"},
        {"consulta": "ok", "limiar": 1.5},
        {"consulta": "ok", "limiar": -0.1},
    ],
)
def test_buscar_validacao_422(cliente, corpo):
    assert cliente.post("/api/buscar", json=corpo).status_code == 422


def test_buscar_sem_indice_503(cliente_sem_indice):
    r = cliente_sem_indice.post("/api/buscar", json={"consulta": "imprensa"})
    assert r.status_code == 503
    assert r.json() == {"detail": "Índice não encontrado. Rode python -m jurismatch.indexar."}


def test_buscador_e_criado_uma_vez(dir_indice, dir_pdf, dir_web, embedder_falso):
    chamadas = []

    def fabrica():
        chamadas.append(1)
        return Buscador(dir_indice, embedder=embedder_falso, reranker=RerankerFalso())

    c = TestClient(criar_app(fabrica, dir_indice=dir_indice, dir_pdf=dir_pdf, dir_web=dir_web))
    for _ in range(3):
        assert c.post("/api/buscar", json={"consulta": "imprensa", "rerank": False}).status_code == 200
    assert len(chamadas) == 1


def test_pdf_ok(cliente):
    r = cliente.get("/api/pdf/ADI_1_peticao_inicial.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    assert r.content.startswith(b"%PDF")


@pytest.mark.parametrize(
    "caminho",
    [
        "ADI_999_inexistente.pdf",
        "..%2Fsegredo.pdf",
        "%2e%2e%2fsegredo.pdf",
        "..%5Csegredo.pdf",
        "../segredo.pdf",
        "ADI_1_peticao_inicial.txt",
        "ADI 1.pdf",
    ],
)
def test_pdf_invalido_ou_path_traversal_404(cliente, caminho):
    assert cliente.get(f"/api/pdf/{caminho}").status_code == 404


def test_raiz_serve_index_html(cliente):
    r = cliente.get("/")
    assert r.status_code == 200
    assert "JurisMatch" in r.text


def test_service_worker_servido(cliente):
    r = cliente.get("/sw.js")
    assert r.status_code == 200
    assert "fetch" in r.text
    assert "no-cache" in r.headers["cache-control"]


def test_rotas_api_tem_precedencia_sobre_estaticos(cliente):
    assert cliente.get("/api/status").headers["content-type"].startswith("application/json")


def test_app_sobe_sem_pasta_web(dir_indice, dir_pdf, tmp_path):
    c = TestClient(criar_app(dir_indice=dir_indice, dir_pdf=dir_pdf, dir_web=tmp_path / "nao_existe"))
    assert c.get("/api/status").status_code == 200


def test_buscar_lida_com_arquivo_pdf_nulo(dir_indice, dir_pdf, dir_web, embedder_falso):
    class BuscadorPdfNulo:
        def buscar(self, *args, **kwargs):
            return [{
                "posicao": 1,
                "doc_id": "ADI_1",
                "classe": "ADI",
                "numero": 1,
                "score": 0.9,
                "similaridade": 0.8,
                "chunk_id": "c1",
                "secao": None,
                "trecho": "trecho de teste",
                "arquivo_pdf": None,
                "pagina": 1,
                "metodo_extracao": "nativo",
                "link_pdf": "local/path.pdf",
            }]

    c = TestClient(criar_app(lambda: BuscadorPdfNulo(), dir_indice=dir_indice, dir_pdf=dir_pdf, dir_web=dir_web))
    r = c.post("/api/buscar", json={"consulta": "teste"})
    assert r.status_code == 200
    res = r.json()["resultados"][0]
    assert res["pdf_disponivel"] is False
    assert res["url_pdf"] is None

