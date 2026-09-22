# Coleta das petições iniciais — guia de execução

Guia prático do script de scraping da etapa 1. A explicação de **por que** o script foi feito assim, com as limitações do site do STF e as soluções adotadas, está no [README principal do projeto](../README.md).

## Conteúdo da pasta

| Arquivo / pasta | O que é |
|---|---|
| `baixar_peticoes_stf.py` | Script de coleta (Python + Playwright). |
| `base_inicial_controle_concentrado_stf_2026_09_08.xlsx` | Planilha de entrada, exportada do STF em 08/09/2026: 906 processos e 37 colunas. O script usa só `Processo` e `Link do processo`. |
| `peticoes_processos_estruturantes/` | Saída: PDFs e `log_download.csv`. Ignorada no git. |
| `.perfil_chromium_stf/` | Perfil persistente do Chromium, que guarda o cookie do WAF entre execuções. Ignorada no git. |

## Instalação

```bash
pip install pandas openpyxl playwright
playwright install chromium
```

## Uso

```bash
# 10 primeiras linhas da planilha (padrão), com janela do navegador visível
python baixar_peticoes_stf.py

# 50 processos a partir da linha 100, sem janela
python baixar_peticoes_stf.py -n 50 --inicio 100 --headless

# planilha e pasta de saída alternativas
python baixar_peticoes_stf.py -p outra_planilha.xlsx -o outra_pasta
```

| Argumento | Padrão | Função |
|---|---|---|
| `-n`, `--quantidade` | 10 | Quantas linhas da planilha processar. |
| `--inicio` | 0 | Índice da primeira linha, para retomar de onde parou. |
| `-p`, `--planilha` | a planilha desta pasta | Arquivo de entrada. |
| `-o`, `--saida` | `peticoes_processos_estruturantes` | Pasta de destino. |
| `--headless` | desligado | Roda sem janela. Menos confiável contra o WAF. |

Os padrões ficam no bloco `CONFIGURAÇÃO`, no topo do script. Como o download é incremental e pula o que já existe, a base pode ser completada em várias rodadas.

## O que o script faz, por processo

1. Extrai o número `incidente` do link da planilha.
2. Pula se o PDF já existe na pasta de saída.
3. Abre a página de peças no Chromium e espera o desafio do WAF ser resolvido, até 30 s por tentativa e 3 tentativas.
4. Filtra do HTML os links cujo rótulo **começa** com "Petição inicial", descartando `docID` repetido.
5. Baixa cada PDF pela sessão do navegador, validando o status 200 e a assinatura `%PDF-`. Se voltar 202, renova o token e tenta de novo.
6. Descarta por MD5 as partes que são cópias idênticas e, se sobrar uma só, tira o sufixo `_parteNN` do nome.
7. Grava o resultado no log.

## Saída

**Nomes dos arquivos:** `<Processo>_peticao_inicial.pdf`, com caracteres especiais trocados por `_`. Exemplos: `ADC_27_peticao_inicial.pdf`, `ADI_1234_peticao_inicial_parte02.pdf`.

**Log** (`log_download.csv`, separador `;`, codificação UTF-8 com BOM):

| Coluna | Conteúdo |
|---|---|
| `processo` | Nome do processo na planilha. |
| `incidente` | Identificador extraído do link. |
| `status` | `ok`, `ja_existia`, `sem_peticao` ou `erro`. |
| `arquivos` | PDFs salvos, separados por `;`. |
| `obs` | Motivo, nos casos `sem_peticao` e `erro`. |

O status `sem_peticao` cobre dois casos: a página informa "Ausência de peça eletrônica", ou nenhuma peça rotulada como petição inicial foi encontrada.

## Problemas comuns

| Sintoma | Causa provável e o que fazer |
|---|---|
| `desafio do WAF não resolvido` repetido | Modo headless. Rode com janela visível. |
| Muitos avisos de resposta 202 | O token do WAF está expirando rápido. O script renova sozinho, mas vale aumentar as pausas `PAUSA_MIN` e `PAUSA_MAX`. |
| `unable to verify the first certificate` | Cadeia TLS incompleta do STF. Já tratado por `ignore_https_errors=True`. Se voltar, confira se o contexto do navegador não foi alterado. |
| Nenhum link encontrado em processos que têm petição | O HTML do site pode ter mudado. Ajuste as regex `RE_ANCHOR` e `RE_PETICAO`. |
