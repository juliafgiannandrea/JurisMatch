# JurisMatch

Projeto sobre as **petições iniciais dos processos de controle concentrado de constitucionalidade do STF** (ADI, ADPF, ADC e ADO).

---

# Etapa 1 — Scraping e extração das petições iniciais

A primeira etapa monta a base documental do projeto: baixar do site do STF o PDF da petição inicial de cada processo de controle concentrado. Sem esses documentos não há o que analisar nas etapas seguintes, então tudo começa aqui.

O ponto de partida é a planilha `base_inicial_controle_concentrado_stf_2026_09_08.xlsx`, exportada do painel de estatísticas do STF em 08/09/2026. Ela traz **906 processos** (635 ADI, 236 ADPF, 20 ADC e 15 ADO) com 37 colunas de metadados, mas **nenhum documento**: só o link para a página de cada processo no portal. A tarefa da etapa 1 é percorrer esses links e trazer os PDFs. Das 100 primeiras linhas já processadas, 97 renderam a petição inicial em PDF.

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

Como o endereço do passo 2 é previsível a partir do `incidente`, o script extrai esse número do link da planilha e vai direto para a lista de peças, pulando a página do portal.

## Limitações do site e as soluções adotadas

Esta é a parte central da etapa. Cada obstáculo encontrado no site do STF exigiu uma decisão de implementação.

### 1. O site é protegido por AWS WAF com desafio JavaScript

**A limitação.** O domínio `redir.stf.jus.br`, onde ficam tanto a lista de peças quanto os PDFs, está atrás do **AWS WAF** (Web Application Firewall) configurado com a ação **challenge**. Uma requisição HTTP comum, feita com `requests`, `curl` ou `httpx`, não recebe o conteúdo: volta um **HTTP 202 com corpo vazio** e o cabeçalho `x-amzn-waf-action: challenge`.

Para ser atendido, o cliente precisa mandar o cookie **`aws-waf-token`**. Esse cookie só é emitido depois que o navegador carrega uma página interstitial e **executa um script de desafio em JavaScript**, que faz uma verificação e recarrega a página sozinho. Não é um captcha, não pede interação humana: o que ele testa é se do outro lado existe um navegador real, capaz de rodar JavaScript e devolver a prova esperada. Um script Python que só fala HTTP nunca passa por isso.

Pior: o **token expira**. No meio de uma sequência de downloads, o 202 vazio volta a aparecer e é preciso refazer o desafio.

**A solução: Playwright controlando um Chromium real.** Essa limitação é o motivo de a etapa usar automação de navegador em vez da dupla `requests` + `BeautifulSoup`, que seria o caminho natural para raspar uma página estática. O Playwright foi escolhido por quatro razões:

- **Ele resolve o desafio sem código extra.** Como controla um Chromium de verdade, basta abrir a página de peças e esperar. O script do WAF executa, o cookie é emitido e a página real carrega. A função `passou_no_desafio` detecta o fim do desafio procurando no HTML marcadores da página verdadeira, e não da interstitial.
- **O download reaproveita a sessão do navegador.** O objeto `context.request` do Playwright faz requisições HTTP com **os mesmos cookies do Chromium**. O PDF é baixado com um GET simples e gravado em bytes, sem precisar renderizar o arquivo numa aba, interceptar eventos de download ou lidar com o visualizador de PDF do navegador. É a melhor parte da solução: o navegador cuida da autenticação, o download continua sendo HTTP puro.
- **Renovação automática do token.** Quando o GET devolve 202 de novo, o script recarrega a página de peças no navegador para obter um token novo e repete o download, até três tentativas.
- **Perfil persistente.** Com `launch_persistent_context`, o perfil do Chromium é gravado em `.perfil_chromium_stf/`. O cookie do WAF sobrevive entre execuções, então nem toda rodada precisa refazer o desafio do zero.

### 2. O WAF também avalia o comportamento do cliente

**A limitação.** Além do desafio, sistemas desse tipo observam sinais de automação e o ritmo das requisições. Um navegador controlado por script expõe a propriedade `navigator.webdriver`, e uma rajada de downloads sem pausa é um padrão óbvio de robô.

**A solução.** O Chromium sobe com a flag `--disable-blink-features=AutomationControlled`, que remove esse sinal, com `locale="pt-BR"` e viewport de tamanho normal. Entre um processo e outro há uma **pausa aleatória de 1,5 a 4 segundos**, e entre PDFs do mesmo processo, de 0,5 a 1,5 segundo. O padrão é rodar com **janela visível** (`HEADLESS = False`), que se mostrou mais confiável contra o WAF do que o modo headless. O objetivo aqui é duplo: passar pelo filtro e não sobrecarregar um servidor público.

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

**A solução.** Três mecanismos. O tratamento de exceções isola cada processo, então uma falha vira uma linha de status `erro` no log em vez de interromper a execução. O download é **incremental**: `PULAR_JA_BAIXADOS` verifica se o PDF já existe na pasta e pula. E os argumentos `--inicio` e `--quantidade` permitem fatiar a planilha e coletar em várias rodadas. Ao final, o `log_download.csv` registra processo, incidente, status, arquivos gerados e observação, o que torna possível auditar o que faltou e rodar de novo só nesses casos.

## Resultado até agora

As rodadas já executadas cobriram as **100 primeiras linhas da planilha**, com o seguinte resultado:

| Resultado | Processos |
|---|---|
| Petição inicial baixada | 97 |
| Sem peça eletrônica | 3 |
| Erros | 0 |

São 102 arquivos PDF e cerca de 172 MB, porque algumas petições vêm divididas em partes. Os três processos sem peça eletrônica são ADI 3159, ADI 3596 e ADI 4245, todos anteriores a 2010. Os PDFs ficam em `peticoes_processos_estruturantes/`, fora do controle de versão. A coleta das 906 linhas continua em rodadas sucessivas com `--inicio`.

Em 90 acessos seguidos não apareceu um único aviso de renovação de token do WAF, o que indica que o perfil persistente do Chromium segura bem o cookie entre requisições.

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

Ou seja, **42% das páginas não têm camada de texto** e vão exigir OCR. A digitalização se concentra nos processos antigos, mas não se limita a eles: ADC 96 e ADC 98, ambas de 2025, vieram inteiramente escaneadas. A data de autuação, portanto, não serve para prever se um arquivo precisa de OCR. Existem ainda seis documentos mistos, com páginas nativas e digitalizadas no mesmo PDF, o que obriga a decidir página a página.

---

# Etapa 2 — Extração do texto

Transforma os PDFs em arquivos de texto, um por petição, com OCR acionado apenas nas páginas que precisam. O detalhamento está no [README da etapa 2](extracao_texto_peticoes/README.md).

Resultado sobre os 102 arquivos já coletados:

| Medida | Valor |
|---|---|
| Arquivos processados | 102 de 102 |
| Páginas | 4.449 |
| Páginas por OCR | 1.902 |
| Caracteres extraídos | 7,8 milhões |
| Erros | 0 |
| Tempo de parede | 19 minutos |

A decisão entre texto nativo e OCR é tomada página a página, combinando quantidade de texto com área coberta por imagem. Cada página do arquivo de saída é marcada com a origem do texto, o que permite saber depois quais trechos vieram de OCR e são menos confiáveis.

---

# Métricas e benchmark

Dois scripts para avaliar a extração, descritos no [README de métricas](metricas/README.md). Foram feitos para o benchmark contra outras soluções, então pontuam qualquer pasta de `.txt`, não só a deste projeto.

O primeiro mede cobertura, volume, qualidade léxica e presença de estrutura jurídica, sem precisar de gabarito. O segundo mede o erro do OCR com gabarito real, construído a partir das páginas que já têm texto nativo.

Uma observação metodológica que saiu dessa medição: avaliar só por erro de caractere leva a conclusão errada neste corpus. A tarja de assinatura digital do STF é texto vertical na margem e aparece em posições diferentes no extrator nativo e no OCR, o que desloca blocos inteiros e infla a distância de edição sem que nenhuma palavra tenha sido lida errado. Por isso o benchmark reporta também métricas insensíveis à ordem.

## O que fica para a próxima etapa

- Completar a coleta das 906 linhas da planilha e reexecutar a extração sobre o corpus inteiro.
- Estruturar o texto extraído para a análise, aproveitando os marcadores de origem por página.

## Estrutura do repositório

```
JurisMatch/
├── README.md                                    # este arquivo
├── scrapping_processos_controle_concentrado/    # etapa 1: coleta
│   ├── README.md                                # guia de instalação e execução
│   ├── baixar_peticoes_stf.py                   # script de coleta
│   ├── base_inicial_...stf_2026_09_08.xlsx      # planilha de entrada (906 processos)
│   ├── peticoes_processos_estruturantes/        # saída: PDFs + log (ignorada no git)
│   └── .perfil_chromium_stf/                    # perfil do Chromium (ignorada no git)
├── extracao_texto_peticoes/                     # etapa 2: extração de texto
│   ├── README.md                                # critério, desempenho e limitações
│   ├── extrair_texto_peticoes.py                # PyMuPDF + OCR por página
│   └── texto_peticoes/                          # saída: .txt + log (ignorada no git)
└── metricas/                                    # avaliação e benchmark
    ├── README.md                                # o que cada métrica significa
    ├── metricas_extracao.py                     # pontua qualquer saída de extração
    └── benchmark_ocr.py                         # CER, WER e F1 contra gabarito
```
