# Frontend PWA do JurisMatch (substitui o Streamlit)

Branch: `issue_frontend`. Data: 2026-11-10.

## Objetivo

Trocar a interface Streamlit (`app/app.py`) por um PWA instalável (celular e desktop), servido por uma API
FastAPI que reaproveita o `jurismatch.busca.Buscador` sem mudar a lógica de busca.

Um comando só para rodar tudo: `python -m jurismatch.api` (sobe em http://127.0.0.1:8000, serve API + PWA).

## Arquitetura

```
app/web/            PWA estático, sem etapa de build (HTML + CSS + JS puro, ES modules)
src/jurismatch/api.py   FastAPI: /api/* + arquivos estáticos de app/web na raiz "/"
```

- Sem Node, sem bundler: a turma roda só com Python.
- A API monta `app/web` em `/` (com `html=True`), DEPOIS das rotas `/api`. O `sw.js` e o
  `manifest.webmanifest` ficam na raiz de `app/web` para o service worker ter escopo `/`.
- `config.py` ganha `DIR_WEB = RAIZ / "app" / "web"`.

## Contrato da API (fonte da verdade entre backend e frontend)

### `GET /api/status`
```json
{"indice_pronto": true, "buscador_carregado": false, "peticoes": 97, "trechos": 5123,
 "modelo_embedding": "intfloat/multilingual-e5-base", "modelo_reranker": "BAAI/bge-reranker-v2-m3",
 "limiar_padrao": 0.8, "modos": ["hibrido", "denso", "lexical"], "classes": ["ADI", "ADC", "ADO", "ADPF"]}
```
- `indice_pronto`: existe `DIR_INDICE/chunks.parquet` e `faiss.index`. Se falso, `peticoes` e `trechos` = null.
- Não carrega modelo nenhum (resposta instantânea). Contagens vêm do parquet lido uma vez.

### `POST /api/buscar`
Corpo:
```json
{"consulta": "liberdade de imprensa", "k": 5, "modo": "hibrido", "classe": null, "rerank": true, "limiar": 0.8}
```
Validação (pydantic): consulta 1..500 chars (strip, vazia = 422); k 1..20; modo em MODOS; classe null ou
ADI/ADC/ADO/ADPF; limiar 0..1.

Resposta 200:
```json
{"consulta": "...", "rerank": true, "limiar": 0.8, "tempo_ms": 812,
 "resultados": [{"posicao": 1, "doc_id": "ADI_1", "classe": "ADI", "numero": 1, "score": 0.93,
   "similaridade": 0.81, "chunk_id": "...", "secao": "...", "trecho": "...", "arquivo_pdf": "ADI_1_peticao_inicial.pdf",
   "pagina": 3, "metodo_extracao": "nativo", "pdf_disponivel": true, "url_pdf": "/api/pdf/ADI_1_peticao_inicial.pdf#page=3",
   "url_stf": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=1234567"}]}
```
- Mesmos campos do `Buscador._resultados`, SEM `link_pdf` (caminho local), COM `pdf_disponivel`, `url_pdf` e `url_stf`.
- `url_stf`: link oficial do processo no portal do STF (`config.URL_PROCESSO_STF`), ou null quando o doc_id não
  tem incidente numérico em `data/01_raw/pdf/log_download.csv` (colunas `processo;incidente;...`, processo com
  espaço trocado por `_` = doc_id; arquivo ausente = mapa vazio). Mapa carregado uma vez em `criar_app`
  (parâmetro `arq_incidentes`). O frontend mostra o botão "Ver no STF" (nova aba) só quando não for null.
- `secao` pode ser null. Converter NaN/numpy para tipos JSON.
- Índice ausente: 503 `{"detail": "Índice não encontrado. Rode python -m jurismatch.indexar."}`.
- Buscador carregado de forma preguiçosa na 1ª busca, com lock (um carregamento só); `buscar` também
  protegido por lock (modelos não são thread-safe). Endpoints `def` (threadpool), não `async def`.

### `GET /api/pdf/{arquivo}`
- Só nomes que casam `^[A-Za-z0-9_.-]+\.pdf$` e que, resolvidos, ficam dentro de `config.DIR_PDF`. Senão 404.
- `FileResponse` com `media_type="application/pdf"` e `Content-Disposition: inline` (abre no visor do navegador,
  o `#page=N` funciona).

### Testabilidade
`criar_app(fabrica_buscador=None, dir_indice=config.DIR_INDICE, dir_pdf=config.DIR_PDF, dir_web=config.DIR_WEB)`
devolve o app. Testes passam uma fábrica com o `Buscador` montado sobre o índice de teste (ver `tests/test_busca.py`,
fixture com `construir_indice` + `EmbedderFalso`). Módulo expõe `app = criar_app()` e `main()` com uvicorn
(`--host`, `--port`, padrão 127.0.0.1:8000).

## PWA (app/web)

Arquivos: `index.html`, `styles.css`, `app.js` (pode quebrar em módulos), `sw.js`, `manifest.webmanifest`,
`icons/` (SVG + PNG 192, 512 e 512 maskable, apple-touch-icon 180).

Funcional (paridade com o Streamlit + o que faz ser PWA):
1. Campo de consulta grande, Enter busca. Exemplos clicáveis quando vazio.
2. Opções: k (1 a 20), modo (Híbrido / Só semântico / Só palavras), classe (Todas, ADI, ADC, ADO, ADPF),
   reranker (liga/desliga, aviso de ~40 s em CPU), relevância mínima (0,5 a 1,0, passo 0,05, só com reranker).
   Desktop: painel lateral. Celular: folha inferior (bottom sheet). Opções lembradas em localStorage.
3. Resultado em cartões: posição, "ADI 1234", relevância (com reranker: %, barra) ou "Score RRF" (sem
   reranker, explicar que só ordena), similaridade, seção, arquivo + página, método de extração, trecho
   (termos da consulta destacados, recolhível se longo), botão "Abrir PDF na p. N" (nova aba) quando
   `pdf_disponivel`, botão copiar referência.
4. Estados: carregando (com segundos decorridos e botão Cancelar via AbortController; avisar que a 1ª busca
   carrega os modelos), vazio (mensagens do Streamlit: com reranker cita o limiar), erro, índice ausente
   (lê `/api/status`), offline.
5. Histórico local das últimas buscas (localStorage, máx 10), reaplicável e apagável.
6. Última resposta salva localmente: offline, mostra os últimos resultados com aviso "você está offline".
7. Service worker: pré-cache do app shell (versão no nome do cache, limpa caches antigos no activate);
   `/api/*` sempre rede (nunca cachear busca nem PDF). Navegação offline cai no shell.
8. Instalação: botão "Instalar app" via `beforeinstallprompt`; dica para iOS (Compartilhar > Adicionar à Tela).
9. Aviso de nova versão quando o SW atualiza ("Atualizar").
10. URL compartilhável: `/?q=...` executa a busca ao abrir.

Visual (prioridade: não pode ter cara de feito por IA):
- Editorial/jurídico: fundo papel quente, tinta escura, um acento sóbrio (verde-escuro ou vinho), nada de
  gradiente roxo, nada de emoji como ícone, nada de glassmorphism.
- Serif para títulos e número do processo (pilha de fontes do sistema: "Iowan Old Style", "Palatino Linotype",
  Georgia, serif); UI em `system-ui`. Sem fontes remotas (funciona offline).
- Tema claro e escuro (`prefers-color-scheme`), tokens em `:root`.
- Mobile first, alvo de toque >= 44 px, foco visível, contraste AA, `aria-live` nos resultados,
  `prefers-reduced-motion`. Ícones em SVG inline.
- Textos em pt-BR, sem travessão "—".

## Fora de escopo
Mudar busca, índice ou modelos. Autenticação. Deploy.

## Rodar
```bash
pip install -e ".[app]"         # app = fastapi + uvicorn
python -m jurismatch.api        # http://127.0.0.1:8000
```
Precisa do índice em `vectorstore/` (`python -m jurismatch.indexar`). Sem índice o PWA abre e mostra o aviso.
