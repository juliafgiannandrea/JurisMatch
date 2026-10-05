# Etapa 2 — Extração do texto das petições

Transforma os PDFs coletados na etapa 1 em arquivos de texto, um por petição. O script é [`extrair_texto_peticoes.py`](extrair_texto_peticoes.py).

O ponto de partida é uma medição, não uma suposição. Analisando as 4.536 páginas dos 102 PDFs já baixados:

| Tipo de página | Quantidade | Fração |
|---|---|---|
| Texto nativo | 2.630 | 58% |
| Digitalizada, sem texto | 1.902 | 42% |
| Vazia ou só assinatura | 4 | menos de 1% |

| Tipo de documento | Arquivos |
|---|---|
| Todo nativo | 65 |
| Todo digitalizado | 31 |
| Misto | 6 |

Três conclusões vieram desses números e determinam o desenho do script.

1. **Não dá para usar só o extrator de texto.** Quase metade das páginas não tem camada de texto e ficaria vazia.
2. **Não dá para usar só OCR.** As 58% de páginas nativas já têm o texto exato no PDF. Rodar OCR nelas é mais lento e introduz erros onde hoje não existe nenhum.
3. **A decisão tem que ser por página, não por documento.** Seis arquivos misturam páginas nativas e digitalizadas. A segunda parte da ADI 3494, por exemplo, tem 66 páginas nativas e 37 escaneadas.

Vale registrar o que **não** funciona como critério: a data de autuação. A digitalização se concentra em processos antigos, mas ADC 96 e ADC 98, ambas de 2025, vieram inteiramente escaneadas.

## O critério de decisão

Para cada página, nesta ordem:

| Condição | Ação |
|---|---|
| Texto nativo com 100 caracteres ou mais | Usa o texto do próprio PDF |
| Menos de 100 caracteres e imagem cobrindo ao menos metade da página | Roda OCR |
| Menos de 100 caracteres e sem imagem grande | Marca como vazia, não faz nada |

A segunda condição da terceira linha é o detalhe que evita desperdício. Páginas de assinatura e de fecho têm pouco texto e nenhuma imagem grande. Sem checar a cobertura de imagem, o OCR rodaria nelas e não devolveria nada útil. Na validação, quatro páginas caíram nesse caso e nenhuma digitalização real foi classificada errado.

A cobertura de imagem só é calculada nas páginas que já falharam no teste de texto, e usa `page.get_image_info()`. A alternativa óbvia, `page.get_text("dict")`, decodifica os bytes das imagens e mediu de 35 a 465 vezes mais lento, com resultado idêntico.

## Por que PyMuPDF e não pdfplumber

Os dois foram comparados nas 371 páginas da primeira amostra.

| Método | Velocidade |
|---|---|
| PyMuPDF, modo padrão | 650 páginas/s |
| PyMuPDF com `sort=True` | 79 páginas/s |
| pdfplumber | 13,7 páginas/s |

A saída é praticamente a mesma: similaridade média de 0,998 e mediana de 1,000 entre PyMuPDF com `sort=True` e pdfplumber, sem nenhuma página abaixo de 0,87. Nos poucos casos em que divergem, o PyMuPDF extrai mais texto, não menos. O `sort=True` importa porque devolve os blocos na ordem de leitura, o que corrige textos justificados que o modo padrão quebra em linhas soltas.

O pdfplumber levaria cerca de 41 minutos para as 33 mil páginas estimadas, contra 7 do PyMuPDF, sem ganho de qualidade. Ele só valeria a pena para extração de tabelas, que petições quase não têm.

## Instalação

```bash
pip install pymupdf
sudo apt install tesseract-ocr tesseract-ocr-por
```

O pacote `tesseract-ocr-por` é obrigatório. Sem ele o tesseract tenta ler português com o modelo de inglês e o resultado fica inutilizável. O script verifica na partida se o idioma está instalado e aborta com instrução de instalação se não estiver.

## Uso

```bash
# extrai tudo, usando todos os núcleos
python extrair_texto_peticoes.py

# passada rápida, só texto nativo, para saber quanto precisaria de OCR
python extrair_texto_peticoes.py --sem-ocr

# teste em poucos arquivos
python extrair_texto_peticoes.py --limite 5
```

| Argumento | Padrão | Função |
|---|---|---|
| `-e`, `--entrada` | pasta de PDFs da etapa 1 | Onde estão os PDFs. |
| `-o`, `--saida` | `texto_peticoes` | Onde gravar os `.txt` e o log. |
| `-j`, `--processos` | todos os núcleos | Paralelismo. |
| `--limite` | 0 | Processa só os N primeiros, para teste. |
| `--dpi` | 300 | Resolução de rasterização para o OCR. |
| `--idioma` | `por` | Idioma do tesseract. |
| `--min-chars` | 100 | Limiar de texto nativo por página. |
| `--min-cobertura` | 0.5 | Fração de imagem para considerar digitalização. |
| `--sem-ocr` | desligado | Não roda OCR, só marca as páginas pendentes. |
| `--sem-marcadores` | desligado | Não grava as linhas de marcação de página. |
| `--forcar` | desligado | Reprocessa mesmo o que já tem `.txt`. |

Como na etapa 1, o processamento é incremental: arquivos que já têm `.txt` são pulados, então a extração pode ser feita em várias rodadas.

## Saída

Um arquivo `.txt` por PDF, com o mesmo nome base. Por padrão, cada página é precedida por uma linha de marcação:

```
[[pagina 6 | ocr]]
```

O método é `nativo`, `ocr`, `vazia` ou `ocr_falhou`. Essa marcação é o registro de procedência do texto, e existe por um motivo prático: **o texto vindo de OCR contém erros de reconhecimento**, sobretudo em tabelas e em documentos datilografados antigos. Quem for consumir o texto nas etapas seguintes precisa saber quais trechos são confiáveis. Para obter o texto puro, basta remover as linhas que casam com `^\[\[pagina \d+ \| \w+\]\]$`, ou rodar com `--sem-marcadores`.

O log `log_extracao.csv`, com separador `;`, traz uma linha por arquivo:

| Coluna | Conteúdo |
|---|---|
| `arquivo` | Nome do PDF de origem. |
| `paginas` | Total de páginas. |
| `pags_nativas` | Páginas com texto extraído do PDF. |
| `pags_ocr` | Páginas reconhecidas por OCR. |
| `pags_vazias` | Páginas sem texto e sem imagem grande. |
| `chars` | Caracteres no texto final. |
| `metodo` | `nativo`, `ocr`, `misto` ou `vazio`. |
| `segundos` | Tempo de processamento do arquivo. |
| `status` | `ok`, `ok_com_falhas` ou `erro`. |
| `obs` | Motivo, quando houver falha. |

## Desempenho

Medido nesta máquina, com 8 núcleos, sobre páginas digitalizadas reais:

| Operação | Tempo por página |
|---|---|
| Extração de texto nativo | cerca de 0,01 s |
| Rasterização a 300 DPI | cerca de 0,2 s |
| OCR com tesseract | cerca de 1,4 s |

O OCR domina o custo. A 200 DPI o reconhecimento cai para cerca de 1,0 s por página com contagem de palavras quase igual, mas 300 DPI é a resolução recomendada pelo tesseract e foi mantida como padrão, porque o texto jurídico depende de números exatos, como artigos, leis e datas.

O script define `OMP_THREAD_LIMIT=1` antes de paralelizar. O tesseract usa OpenMP e abre várias threads por padrão, o que causa concorrência excessiva quando já existe um processo por núcleo.

## Limitações conhecidas

- **O texto de OCR não é confiável palavra a palavra.** Documentos datilografados dos anos 1990 e 2000 e páginas de tabela produzem erros de reconhecimento. Os marcadores de página permitem isolar esses trechos.
- Os limiares de 100 caracteres e 50% de cobertura foram calibrados nos 102 PDFs já baixados. Valem para o restante do corpus, mas convém reconferir o log quando a coleta das 906 linhas terminar.
- Páginas que são imagem de um gráfico ou de um diagrama, sem texto, vão para o OCR e devolvem pouco ou nada. Aparecem no log com poucos caracteres.
- O script não faz correção ortográfica nem pós-processamento do OCR. A saída é o texto reconhecido como veio.
