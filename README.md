# JurisMatch

Busca semântica nas **petições iniciais dos processos de controle concentrado de constitucionalidade do STF**. Você faz uma consulta em linguagem natural e recebe um ranking de petições, com o trecho mais relevante e a página do PDF onde ele está.

O corpus atual tem **656 petições** (588 ADI, 45 ADPF, 20 ADC e 3 ADO), somando 22.468 páginas e 40.526 trechos indexados. A busca roda pela interface web ou pela linha de comando:

```bash
streamlit run app/app.py
python scripts/05_search.py "liberdade de imprensa e capital estrangeiro" --k 5
```

## Pipeline

O download é feito por `scrapping_processos_controle_concentrado/baixar_peticoes_stf.py`; as demais etapas são scripts em `scripts/`. Cada etapa lê a saída da anterior nas pastas padrão de `data/`. Rodar todas em sequência, sem argumentos, atualiza o índice único em `vectorstore/`, que é o que o front e a busca usam.

| Etapa | Script | Entrada → saída |
|---|---|---|
| 0 | `baixar_peticoes_stf.py -o ../data/01_raw/pdf` | planilha → `data/01_raw/pdf/` |
| 1 | `01_ocr.py` | PDFs → `data/02_processed/ocr/` (texto nativo ou OCR, página a página) |
| 2 | `02_clean.py` | → `data/02_processed/clean/` (remove carimbos, números de página e cabeçalhos) |
| 3 | `03_chunk.py` | → `data/03_chunks/chunks.parquet` e `metadata/documentos.csv` |
| 4 | `04_index.py` | → `vectorstore/` (embeddings, FAISS exato, BM25 e manifesto) |
| 5 | `05_search.py` | consulta → ranking de petições com o melhor trecho de cada uma |

Todas as etapas são incrementais. O download e o OCR pulam os arquivos que já existem, e a indexação só calcula embeddings de trechos novos, reconhecidos pelo hash do texto.

## Como rodar

```bash
source venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[dev,app]"
sudo apt install tesseract-ocr tesseract-ocr-por      # OCR da etapa 1
```

### Acrescentar petições ao corpus

Se a planilha só traz classe e número, sem o link do processo, converta-a primeiro. O script procura o `incidente` na planilha base do STF e, quando não encontra, no portal:

```bash
cd scrapping_processos_controle_concentrado
python preparar_planilha.py "planilha.xlsx" -o casos.xlsx --col-classe SIG_CLASSE_PROCES --col-numero NUM_PROCESSO
python baixar_peticoes_stf.py -p casos.xlsx -o ../data/01_raw/pdf -n 1000    # com janela visível, por causa do WAF
cd ..
```

Depois, rode as etapas seguintes sem argumentos:

```bash
python scripts/01_ocr.py
python scripts/02_clean.py
python scripts/03_chunk.py
python scripts/04_index.py
```

A limpeza e o chunking avisam quando um arquivo parece ter ficado sem OCR. Nesse caso, apague o `.txt` dele em `data/02_processed/ocr/` e rode a etapa 1 de novo.

### Buscar

```bash
streamlit run app/app.py                       # front em http://localhost:8501
python scripts/05_search.py "consulta" --k 10  # linha de comando
```

| Opção | Valores | Função |
|---|---|---|
| `--k` | 1 a 100 no front | Petições no resultado. |
| `--modo` | `hibrido`, `denso`, `lexical` | Semântico + palavras, só semântico ou só BM25. |
| `--classe` | `ADI`, `ADC`, `ADO`, `ADPF` | Filtra por classe. |
| `--limiar` | 0 a 1 (0,5 a 1 no front) | Relevância mínima do reranker. Padrão 0,8. |
| `--sem-rerank` | | Só a busca híbrida, sem o cross-encoder. Bem mais rápido. |
| `--dir-indice` | pasta | Usa outro índice. |

O front e a linha de comando mostram o tempo de cada consulta, separado em recuperação, reranking e total.

### Trocar o modelo de embedding

O modelo padrão fica em `MODELO_EMBEDDING`, em `src/jurismatch/config.py`, e os prefixos de cada modelo estão na tabela `PREFIXOS_POR_MODELO`. Para testar outro modelo sem mexer no índice principal, gere um índice em outra pasta:

```bash
python scripts/03_chunk.py --modelo Qwen/Qwen3-Embedding-0.6B --saida data/qwen3/chunks.parquet --documentos data/qwen3/documentos.csv
python scripts/04_index.py --modelo Qwen/Qwen3-Embedding-0.6B --chunks data/qwen3/chunks.parquet --dir-indice vectorstore_qwen3
python scripts/05_search.py "consulta" --dir-indice vectorstore_qwen3
```

A busca lê o modelo do `manifesto.json` do índice, então a consulta é sempre transformada em vetor pelo mesmo modelo dos trechos. Com `--reaproveitar <outros índices>`, a indexação usa os vetores já calculados por outros índices do mesmo modelo. O embedder usa GPU quando existe, o que permite gerar o índice no Colab e trazer a pasta pronta.

## Testes

```bash
pytest -q                                   # rápido, sem baixar o modelo
JURISMATCH_TESTES_LENTOS=1 pytest -q        # inclui o teste com o modelo real
```

---

# Etapa 1 — Scraping e extração das petições iniciais

A primeira etapa monta a base documental do projeto: baixa do site do STF o PDF da petição inicial de cada processo de controle concentrado. As etapas seguintes dependem desses documentos.

O ponto de partida é a planilha `base_inicial_controle_concentrado_stf_2026_09_08.xlsx`, exportada do painel de estatísticas do STF em 08/09/2026. Ela traz **906 processos** (635 ADI, 236 ADPF, 20 ADC e 15 ADO) com 37 colunas de metadados, mas **nenhum documento**, só o link para a página de cada processo no portal. A etapa 1 percorre esses links e traz os PDFs. Das 100 primeiras linhas já processadas, 97 renderam a petição inicial em PDF.

O código está em [`scrapping_processos_controle_concentrado/baixar_peticoes_stf.py`](scrapping_processos_controle_concentrado/baixar_peticoes_stf.py). Instruções de instalação e execução estão no [README da pasta](scrapping_processos_controle_concentrado/README.md).

## Como o site do STF entrega as peças

Não existe API pública nem download em lote. O caminho até o PDF foi descoberto manualmente, abrindo o site com as ferramentas de desenvolvedor do navegador e observando as requisições de rede. São três saltos:

1. **Página do processo**, que é o link da planilha:
   `portal.stf.jus.br/processos/detalhe.asp?incidente=N`
   O número `incidente` é o identificador interno do processo no STF.

2. **Página de peças**, aberta pelo botão "Peças" e hospedada em outro domínio:
   `redir.stf.jus.br/estfvisualizadorpub/jsp/consultarprocessoeletronico/ConsultarProcessoEletronico.jsf?seqobjetoincidente=N`
   É uma página JSF que lista todas as peças do processo como links.

3. **O PDF**, no endereço para o qual cada peça aponta:
   `redir.stf.jus.br/paginadorpub/paginador.jsp?docTP=TP&docID=X&prcID=N`
   Essa URL devolve o arquivo diretamente, com `Content-Type: application/pdf`.

Como o endereço do passo 2 é previsível a partir do `incidente`, o script extrai esse número do link da planilha e vai direto para a lista de peças, sem passar pela página do portal.

## Limitações do site e as soluções adotadas

Cada obstáculo encontrado no site do STF exigiu uma decisão de implementação.

### 1. O site é protegido por AWS WAF com desafio JavaScript

**A limitação.** O domínio `redir.stf.jus.br`, onde ficam tanto a lista de peças quanto os PDFs, está atrás do **AWS WAF** (Web Application Firewall) configurado com a ação **challenge**. Uma requisição HTTP comum, feita com `requests`, `curl` ou `httpx`, não recebe o conteúdo: volta um **HTTP 202 com corpo vazio** e o cabeçalho `x-amzn-waf-action: challenge`.

Para ser atendido, o cliente precisa mandar o cookie **`aws-waf-token`**. Esse cookie só é emitido depois que o navegador carrega uma página intermediária e **executa um script de desafio em JavaScript**, que faz uma verificação e recarrega a página sozinho. Não é um captcha e não pede interação humana: o teste é se do outro lado existe um navegador real, capaz de rodar JavaScript e devolver a prova esperada. Um script Python que só fala HTTP nunca passa por isso.

Além disso, o **token expira**. No meio de uma sequência de downloads, o 202 vazio volta a aparecer e é preciso refazer o desafio.

**A solução: Playwright controlando um Chromium real.** Por causa dessa limitação, a etapa usa automação de navegador em vez da dupla `requests` + `BeautifulSoup`, que seria o caminho natural para raspar uma página estática. O Playwright foi escolhido por quatro razões:

- **Ele resolve o desafio sem código extra.** Como controla um Chromium de verdade, basta abrir a página de peças e esperar. O script do WAF executa, o cookie é emitido e a página real carrega. A função `passou_no_desafio` detecta o fim do desafio procurando no HTML marcadores da página verdadeira, e não da página intermediária.
- **O download reaproveita a sessão do navegador.** O objeto `context.request` do Playwright faz requisições HTTP com **os mesmos cookies do Chromium**. O PDF é baixado com um GET simples e gravado em bytes, sem precisar renderizar o arquivo numa aba, interceptar eventos de download ou lidar com o visualizador de PDF do navegador. O navegador cuida da autenticação e o download continua sendo HTTP puro.
- **Renovação automática do token.** Quando o GET devolve 202 de novo, o script recarrega a página de peças no navegador para obter um token novo e repete o download, até três tentativas.
- **Perfil persistente.** Com `launch_persistent_context`, o perfil do Chromium é gravado em `.perfil_chromium_stf/`. O cookie do WAF sobrevive entre execuções, então nem toda rodada precisa refazer o desafio do zero.

### 2. O WAF também avalia o comportamento do cliente

**A limitação.** Além do desafio, sistemas desse tipo observam sinais de automação e o ritmo das requisições. Um navegador controlado por script expõe a propriedade `navigator.webdriver`, e uma rajada de downloads sem pausa é um padrão óbvio de robô.

**A solução.** O Chromium sobe com a flag `--disable-blink-features=AutomationControlled`, que remove esse sinal, com `locale="pt-BR"` e viewport de tamanho normal. Entre um processo e outro há uma **pausa aleatória de 1,5 a 4 segundos**, e entre PDFs do mesmo processo, de 0,5 a 1,5 segundo. O padrão é rodar com **janela visível** (`HEADLESS = False`), que se mostrou mais confiável contra o WAF do que o modo headless. O objetivo é duplo: passar pelo filtro e não sobrecarregar um servidor público.

### 3. A cadeia de certificados TLS vem incompleta

**A limitação.** O servidor `redir.stf.jus.br` serve a cadeia de certificados sem o certificado intermediário. Navegadores toleram a falha, porque conseguem completar a cadeia por conta própria, mas clientes HTTP mais estritos não. O cliente interno do Playwright, que roda em Node, falha com `unable to verify the first certificate` e o download morre antes de começar.

**A solução.** O contexto do navegador é criado com `ignore_https_errors=True`. É uma concessão consciente, aceitável porque o domínio de destino é fixo e conhecido.

### 4. Os rótulos das peças são inconsistentes

**A limitação.** A lista de peças é HTML legado, sem identificadores estáveis nem classe própria para o tipo de documento. O que distingue uma peça de outra é o **texto do link**, e esse texto é bagunçado. O tipo da peça aparece antes de um travessão, como em `Petição inicial - Petição Inicial 1`, mas a expressão "petição inicial" também aparece no meio do rótulo de outros documentos, como `Documento comprobatório - ... Petição Inicial`. Uma busca ingênua por "petição inicial" traria anexos e comunicações junto.

**A solução.** A regex `RE_PETICAO` é **ancorada no início do rótulo** (`^\s*peti[cç][aã]o\s+inicial\b`), aceitando as variações de acentuação. Só entram peças cujo tipo é petição inicial, não as que a mencionam de passagem.

### 5. O mesmo documento aparece em `docID`s diferentes

**A limitação.** O STF às vezes registra o mesmo arquivo mais de uma vez na lista de peças, com identificadores distintos. Baixar todos geraria PDFs duplicados na base.

**A solução.** Duas camadas de deduplicação. Primeiro, links repetidos são descartados pelo `docID` antes do download. Depois, o **MD5 de cada PDF baixado** é comparado com os anteriores do mesmo processo, e cópias idênticas são apagadas do disco. Essa segunda camada pega os casos em que o conteúdo é igual embora o identificador seja diferente.

### 6. A petição inicial pode estar dividida em várias peças

**A limitação.** Petições longas são cadastradas em partes, cada uma como uma peça separada.

**A solução.** Todas as partes são baixadas e nomeadas com sufixo `_parte01`, `_parte02` e assim por diante. Se depois da deduplicação sobrar só um arquivo, ele é renomeado para o nome simples, sem sufixo, para manter o padrão da base.

### 7. Nem todo processo tem peça eletrônica pública

**A limitação.** Processos antigos, digitalizados só em parte, ou com visualização restrita, não expõem PDF ao público. A página de peças responde com a mensagem "Ausência de peça eletrônica".

**A solução.** O script não trata isso como erro. Detecta a mensagem, registra o processo com status `sem_peticao` no log e segue para o próximo. Assim a ausência fica documentada e é possível distinguir "não existe" de "falhou ao baixar".

### 8. Um erro no meio derruba a coleta inteira

**A limitação.** São 906 processos. Um timeout ou uma falha de rede no processo 300 não pode obrigar a recomeçar do zero.

**A solução.** Três mecanismos. O tratamento de exceções isola cada processo, então uma falha vira uma linha de status `erro` no log em vez de interromper a execução. O download é **incremental**: `PULAR_JA_BAIXADOS` verifica se o PDF já existe na pasta e pula. E os argumentos `--inicio` e `--quantidade` permitem fatiar a planilha e coletar em várias rodadas. Ao final, o `log_download.csv` registra processo, incidente, status, arquivos gerados e observação, o que permite auditar o que faltou e rodar de novo só nesses casos.

## Resultado até agora

O corpus atual tem 664 PDFs (656 petições, cerca de 740 MB). Eles vieram das primeiras linhas da planilha base e de duas planilhas de casos de teste, uma delas com 432 ADIs marcadas quanto à impugnação de medida provisória. Os PDFs ficam em `data/01_raw/pdf/`, fora do controle de versão.

As medições abaixo são da **primeira rodada**, que cobriu as 100 primeiras linhas da planilha:

| Resultado | Processos |
|---|---|
| Petição inicial baixada | 97 |
| Sem peça eletrônica | 3 |
| Erros | 0 |

São 102 arquivos PDF e cerca de 172 MB, porque algumas petições vêm divididas em partes. Os três processos sem peça eletrônica são ADI 3159, ADI 3596 e ADI 4245, todos anteriores a 2010. A coleta das 906 linhas continua em rodadas sucessivas com `--inicio`.

Em 90 acessos seguidos não apareceu nenhum aviso de renovação de token do WAF, o que indica que o perfil persistente do Chromium segura bem o cookie entre requisições.

### Quanto desse material é digitalização

Medição das 4.536 páginas dos 102 arquivos, feita com PyMuPDF, classificando cada página pela quantidade de texto nativo e pela área coberta por imagem:

| Tipo de página | Quantidade |
|---|---|
| Texto nativo | 2.630 |
| Digitalizada, sem texto | 1.902 |
| Vazia ou só assinatura | 4 |

| Tipo de documento | Arquivos |
|---|---|
| Todo nativo | 65 |
| Todo digitalizado | 31 |
| Misto | 6 |

Ou seja, **42% das páginas não têm camada de texto** e precisam de OCR. A digitalização se concentra nos processos antigos, mas não se limita a eles: ADC 96 e ADC 98, ambas de 2025, vieram inteiramente escaneadas. A data de autuação, portanto, não serve para prever se um arquivo precisa de OCR. Há ainda seis documentos mistos, com páginas nativas e digitalizadas no mesmo PDF, o que obriga a decidir página a página.

---

# Etapa 2 — Extração do texto

Transforma os PDFs em arquivos de texto, um por petição, com OCR acionado apenas nas páginas que precisam. O detalhamento está no [README da etapa 2](extracao_texto_peticoes/README.md).

Resultado na primeira rodada, com 102 arquivos. No corpus atual, de 664 arquivos, são 22.468 páginas, das quais 2.759 por OCR.

| Medida | Valor |
|---|---|
| Arquivos processados | 102 de 102 |
| Páginas | 4.449 |
| Páginas por OCR | 1.902 |
| Caracteres extraídos | 7,8 milhões |
| Erros | 0 |
| Tempo de parede | 19 minutos |

A decisão entre texto nativo e OCR é tomada página a página, combinando quantidade de texto com área coberta por imagem. Cada página do arquivo de saída é marcada com a origem do texto, o que permite saber depois quais trechos vieram de OCR e são menos confiáveis.

O carimbo de assinatura digital que o STF imprime em toda página ("Documento assinado digitalmente conforme MP n° 2.200-2/2001…") tem mais de 100 caracteres e é descontado antes da contagem. Sem isso, uma página escaneada parecia ter texto nativo e o OCR era pulado. Foi o que aconteceu com ADI 4271, 4376 e 4393, já reprocessadas.

---

# Etapas 3 a 5 — Chunking, indexação e busca

Código em `src/jurismatch/`, com os parâmetros centralizados em `src/jurismatch/config.py`. O estudo que justifica as escolhas abaixo está em `docs/pesquisa/`.

- **Limpeza (etapa 2).** Remove carimbos de assinatura, números de página, cabeçalhos repetidos e linhas sem conteúdo. Os marcadores de página continuam no texto, para cada trecho saber de que página veio.
- **Chunking (etapa 3).** Os textos são cortados por seção e parágrafo, com alvo de 350 tokens e teto de 480, contados com o tokenizador do modelo de embedding. Cada chunk recebe um cabeçalho no formato `ADI 1234 | seção`. A saída é `data/03_chunks/chunks.parquet`, e `metadata/documentos.csv` resume cada petição.
- **Embeddings (etapa 4).** Modelo `intfloat/multilingual-e5-base` (768 dimensões), com os prefixos `query: ` e `passage: ` e vetores normalizados.
- **Índice vetorial (etapa 4).** FAISS `IndexFlatIP`, ou seja, busca exata: a consulta é comparada com todos os trechos. Com cerca de 40 mil trechos, isso leva milissegundos e não perde nenhum resultado.
- **Índice lexical (etapa 4).** BM25 (`bm25s`) com stopwords e stemmer do português.
- **Ranking (etapa 5).** Os rankings semântico e lexical dos trechos são fundidos por RRF (k = 60). Os 30 melhores trechos vão para o reranker `BAAI/bge-reranker-v2-m3`, um cross-encoder que dá a cada um uma nota de relevância de 0 a 1. Cada petição vale o seu melhor trecho (MaxP), e só entram as que passam do limiar (0,8 por padrão). Sem o reranker, a petição vale o melhor trecho em cada sistema e os rankings de petições são fundidos por RRF.

---

# Métricas e benchmark

Dois scripts para avaliar a extração, descritos no [README de métricas](metricas/README.md). Foram feitos para o benchmark contra outras soluções, então pontuam qualquer pasta de `.txt`, não só a deste projeto.

O primeiro mede cobertura, volume, qualidade léxica e presença de estrutura jurídica, sem precisar de gabarito. O segundo mede o erro do OCR com gabarito real, construído a partir das páginas que já têm texto nativo.

Uma observação metodológica que saiu dessa medição: avaliar só por erro de caractere leva a conclusão errada neste corpus. A tarja de assinatura digital do STF é texto vertical na margem e aparece em posições diferentes no extrator nativo e no OCR. Isso desloca blocos inteiros e infla a distância de edição sem que nenhuma palavra tenha sido lida errado. Por isso o benchmark reporta também métricas insensíveis à ordem.

---

# Limitações conhecidas

- **Não há métrica de qualidade da busca.** Ainda não existe gabarito de consultas com as petições relevantes, então precisão, recall e NDCG não são medidos. A coluna `MP` da planilha de casos de teste serve de gabarito para consultas sobre medida provisória.
- **Consultas genéricas diluem a busca semântica.** Em "ação direta de inconstitucionalidade por medida provisória", a primeira parte descreve todo o corpus e pesa no vetor da consulta. O modo lexical e o reranker compensam parte disso.
- **O reranker limita o resultado a 30 trechos.** Com ele ligado, o resultado nunca passa de 30 petições, mesmo com k maior. O cross-encoder leva cerca de 1 s por trecho em CPU.
- **O link do PDF aponta sempre para `data/01_raw/pdf/`**, mesmo quando a busca usa outro índice.
- **O texto de OCR não é confiável palavra a palavra**, sobretudo em documentos datilografados e tabelas.
- Anexos digitalizados e notas de rodapé não são separados do corpo da petição.
- A detecção de seções é heurística (títulos numerados).
- A `ADI_4966` aparece no aviso de "voltar para o OCR" da limpeza, mas é um falso alarme: a página sinalizada é só de assinatura.

# Próximos passos

- Montar um gabarito de consultas e um script de avaliação (recall@k, precisão@k, MRR e NDCG), com média e p95 dos tempos.
- Trazer os metadados da planilha do STF (Ramo do Direito, Assuntos, Legislação, Situação da decisão final) para os trechos e usá-los como filtro. O tipo de norma impugnada, extraído da coluna Legislação, é o candidato mais útil.
- Comparar o `e5-base` com `BAAI/bge-m3` e `Qwen/Qwen3-Embedding-0.6B` usando o gabarito.
- Completar a coleta das 906 linhas da planilha base.

# Estrutura do repositório

```
JurisMatch/
├── README.md                                    # este arquivo
├── pyproject.toml                               # pacote jurismatch e dependências
├── app/app.py                                   # front (Streamlit)
├── scripts/                                     # uma entrada por etapa: 01_ocr ... 05_search (00_download está vazio)
├── src/jurismatch/                              # código das etapas 2 a 5
│   ├── config.py                                # caminhos, modelos, prefixos, chunking e ranking
│   ├── paginas.py                               # leitura dos .txt e identificação das petições
│   ├── limpeza.py, pipeline_limpeza.py          # etapa 2: limpeza
│   ├── chunking.py, pipeline_chunks.py          # etapa 3: chunking e metadados
│   ├── embeddings.py                            # wrapper do modelo de embedding
│   ├── indexar.py                               # etapa 4: embeddings, FAISS e BM25
│   ├── lexical.py                               # BM25
│   ├── reranker.py                              # cross-encoder
│   └── busca.py                                 # etapa 5: busca híbrida, reranking e tempos
├── data/
│   ├── 01_raw/pdf/                              # PDFs baixados (ignorada no git)
│   ├── 02_processed/ocr/                        # texto extraído, com marcadores de página
│   ├── 02_processed/clean/                      # texto limpo
│   └── 03_chunks/                               # chunks.parquet e relatório (ignorada no git)
├── metadata/documentos.csv                      # uma linha por petição
├── vectorstore/                                 # índice usado pelo front e pela busca (ignorada no git)
├── scrapping_processos_controle_concentrado/    # coleta
│   ├── README.md                                # guia de instalação e execução
│   ├── baixar_peticoes_stf.py                   # download das petições (Playwright)
│   ├── preparar_planilha.py                     # converte planilha de classe+número para o download
│   └── base_inicial_...stf_2026_09_08.xlsx      # planilha base (906 processos)
├── extracao_texto_peticoes/                     # documentação e versão original do OCR
├── tests/                                       # pytest
├── docs/pesquisa/                               # estudo que embasa as escolhas de stack
└── metricas/                                    # avaliação da extração e benchmark do OCR
```
