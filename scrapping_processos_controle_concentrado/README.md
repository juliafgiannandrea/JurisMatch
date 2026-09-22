# Etapa 1 — Coleta das petições iniciais (scraping do STF)

Esta etapa monta a base documental do JurisMatch: os PDFs das **petições iniciais** dos processos de controle concentrado de constitucionalidade do STF (ADI, ADPF, ADC e ADO). O script [`baixar_peticoes_stf.py`](baixar_peticoes_stf.py) lê a planilha de processos, navega até a página de peças de cada um e salva a petição inicial em disco.

## Conteúdo da pasta

| Arquivo / pasta | O que é |
|---|---|
| `baixar_peticoes_stf.py` | Script de download (Python + Playwright). |
| `base_inicial_controle_concentrado_stf_2026_09_08.xlsx` | Planilha de entrada exportada do portal do STF em 08/09/2026, com 906 processos (635 ADI, 236 ADPF, 20 ADC, 15 ADO) e 37 colunas de metadados. O script usa apenas `Processo` (nome, ex.: `ADC 27`) e `Link do processo`. |
| `peticoes_processos_estruturantes/` | Saída: PDFs baixados e `log_download.csv`. Ignorada no git. |
| `.perfil_chromium_stf/` | Perfil persistente do Chromium usado pelo Playwright (guarda cookies entre execuções). Ignorada no git. |

## Como o site do STF funciona (fluxo descoberto no navegador)

Não existe API pública para baixar peças. O caminho até o PDF foi mapeado abrindo o site com as ferramentas de desenvolvedor do navegador e observando as requisições:

1. **Página do processo** (link que vem na planilha):
   `https://portal.stf.jus.br/processos/detalhe.asp?incidente=N`
   O número `incidente` é o identificador interno do processo e é o único dado que o script extrai desse link.

2. **Página de peças**, aberta pelo botão "Peças":
   `https://redir.stf.jus.br/estfvisualizadorpub/jsp/consultarprocessoeletronico/ConsultarProcessoEletronico.jsf?seqobjetoincidente=N`
   É uma página JSF que lista todas as peças do processo como links `<a>`.

3. **O PDF em si.** Cada peça aponta para
   `https://redir.stf.jus.br/paginadorpub/paginador.jsp?docTP=TP&docID=X&prcID=N`
   e essa URL devolve o PDF diretamente (`Content-Type: application/pdf`). Não há página intermediária de visualização.

Como o passo 1 é previsível a partir do `incidente`, o script pula direto para o passo 2 e monta a URL da página de peças sozinho.

## A segurança do site: AWS WAF com desafio JavaScript

O domínio `redir.stf.jus.br` (onde ficam a lista de peças e os PDFs) está atrás do **AWS WAF (Web Application Firewall)** configurado com a ação **challenge**. Na prática:

- Uma requisição HTTP comum (`requests`, `curl`, `httpx`) recebe **HTTP 202 com corpo vazio** e o cabeçalho `x-amzn-waf-action: challenge`. Não vem HTML nem PDF.
- Para ser atendido, o cliente precisa enviar o cookie **`aws-waf-token`**. Esse token só é emitido depois que o navegador executa um **script de desafio em JavaScript** servido pelo WAF (uma página interstitial que roda o script e recarrega sozinha).
- O desafio **não é um captcha**: não exige interação humana. Ele verifica se quem está do outro lado é um navegador real capaz de executar JavaScript e produzir a prova esperada.
- O token **expira**. Depois de um tempo, o mesmo 202 volta a aparecer e é preciso passar pelo desafio de novo.

Além do WAF, há um detalhe de infraestrutura: a **cadeia de certificados TLS** de `redir.stf.jus.br` é servida incompleta (falta o intermediário). Navegadores toleram isso, mas clientes HTTP estritos, como o do Node usado internamente pelo Playwright, falham com `unable to verify the first certificate`. Por isso o script usa `ignore_https_errors=True`.

## Por que Playwright

O bloqueio acima elimina a abordagem mais simples (baixar com `requests` + `BeautifulSoup`): sem executar JavaScript, nunca se obtém o `aws-waf-token`. Era necessário um **navegador de verdade**. O Playwright foi escolhido porque:

1. **Resolve o desafio sozinho.** Ele controla um Chromium real. Basta abrir a página de peças e esperar; o script do WAF roda, emite o cookie e a página real carrega. A função `passou_no_desafio` detecta isso procurando no HTML marcadores da página verdadeira (`paginador.jsp`, `Processo (`, ou a mensagem "Ausência de peça eletrônica").

2. **Compartilha a sessão com um cliente HTTP.** O `context.request` do Playwright faz requisições HTTP usando os **mesmos cookies do navegador**. Assim, o PDF é baixado com um `GET` simples e salvo em bytes, sem precisar renderizar o PDF na aba, interceptar downloads ou lidar com o visualizador do Chromium. Quando o `GET` devolve 202 de novo (token expirado), o script recarrega a página de peças no navegador para renovar o token e repete.

3. **Perfil persistente.** `launch_persistent_context` grava o perfil do Chromium em `.perfil_chromium_stf/`, então o cookie do WAF sobrevive entre execuções e nem sempre é preciso passar pelo desafio no início.

4. **Menos cara de robô.** O navegador roda com janela visível por padrão (`HEADLESS = False`, que se mostrou mais confiável contra o WAF), com `locale="pt-BR"`, viewport normal e a flag `--disable-blink-features=AutomationControlled`, que remove o sinal `navigator.webdriver` usado por alguns sistemas antibot. Entre um processo e outro há uma pausa aleatória de 1,5 a 4 s, e entre PDFs do mesmo processo, de 0,5 a 1,5 s, para não sobrecarregar o servidor.

Em resumo: o navegador serve para **obter e renovar o token**; o download em si é HTTP puro na mesma sessão.

## O que o script faz, passo a passo

Para cada linha da planilha (limitado por `--quantidade` e `--inicio`):

1. Extrai o `incidente` do `Link do processo` com regex.
2. Se já existe um PDF com o nome esperado na pasta de saída, pula (`PULAR_JA_BAIXADOS`).
3. Abre a página de peças no navegador e espera o desafio do WAF ser resolvido (até 30 s por tentativa, 3 tentativas).
4. Extrai do HTML os links de `paginador.jsp` cujo **rótulo começa com "Petição inicial"**. A regex é ancorada no início do texto de propósito: o tipo da peça vem antes do " - " (ex.: `Petição inicial - Petição Inicial 1`), e sem a âncora seriam capturadas peças como `Documento comprobatório - ... Petição Inicial` ou comunicações que apenas mencionam a petição.
5. Remove duplicatas por `docID` e força `prcID` a ser o incidente da planilha.
6. Baixa cada PDF via `context.request.get`, validando `status == 200` e que o corpo começa com `%PDF-`. Em caso de 202, renova o token e tenta de novo (3 tentativas).
7. Se a petição está dividida em várias peças, salva como `_parte01`, `_parte02`, ... O STF às vezes registra o **mesmo arquivo em `docID`s diferentes**, então o script calcula o MD5 de cada PDF e descarta cópias idênticas. Se sobrar uma só, renomeia para o nome simples.
8. Registra o resultado no log.

### Nomes dos arquivos

`<Processo>_peticao_inicial.pdf`, com espaços e caracteres especiais trocados por `_`. Exemplos: `ADC_27_peticao_inicial.pdf`, `ADI_1234_peticao_inicial_parte02.pdf`.

### Log (`log_download.csv`, separador `;`)

| Coluna | Conteúdo |
|---|---|
| `processo` | Nome do processo na planilha. |
| `incidente` | Identificador extraído do link. |
| `status` | `ok`, `ja_existia`, `sem_peticao` ou `erro`. |
| `arquivos` | PDFs salvos, separados por `;`. |
| `obs` | Motivo em caso de `sem_peticao` ou `erro`. |

`sem_peticao` cobre dois casos: a página de peças informa "Ausência de peça eletrônica" (processo antigo ou com visualização restrita) ou nenhuma peça rotulada como petição inicial foi encontrada.

## Instalação e uso

```bash
pip install pandas openpyxl playwright
playwright install chromium
```

```bash
# baixa as 10 primeiras linhas da planilha (padrão), com janela do navegador visível
python baixar_peticoes_stf.py

# baixa 50 processos a partir da linha 100, sem janela
python baixar_peticoes_stf.py -n 50 --inicio 100 --headless

# planilha e pasta de saída alternativas
python baixar_peticoes_stf.py -p outra_planilha.xlsx -o outra_pasta
```

Os padrões ficam no bloco `CONFIGURAÇÃO` no topo do script. Como o download é incremental (pula o que já existe), a base pode ser completada em várias rodadas rodando o script repetidas vezes com `--inicio` diferentes.

## Limitações conhecidas

- Processos sem peça eletrônica ou com visualização restrita não têm PDF disponível ao público. Ficam registrados como `sem_peticao`.
- O modo headless funciona, mas o WAF se mostrou menos tolerante a ele. Se aparecerem muitos avisos de "desafio do WAF não resolvido", rode com janela visível.
- O script depende da estrutura atual do HTML da página de peças (links `<a>` para `paginador.jsp`). Mudanças no site do STF podem exigir ajuste nas regex `RE_ANCHOR` e `RE_PETICAO`.
- Os PDFs são salvos exatamente como vêm do STF, sem nenhum tratamento. Os 10 baixados na primeira rodada (ADCs) têm camada de texto, mas processos mais antigos podem vir como digitalização sem texto, o que precisa ser verificado na próxima etapa (extração de texto).
