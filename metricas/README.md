# Métricas e benchmark da extração

Dois scripts, com propósitos diferentes. O primeiro pontua qualquer saída de extração e serve para comparar soluções. O segundo mede o erro do OCR contra um gabarito real.

| Script | Responde a quê | Precisa de gabarito |
|---|---|---|
| [`metricas_extracao.py`](metricas_extracao.py) | Quanto foi extraído, e o texto parece bom? | Não |
| [`benchmark_ocr.py`](benchmark_ocr.py) | Quantos caracteres e palavras o OCR erra? | Constrói sozinho |

## Por que dois scripts

Sem gabarito não existe acurácia. Dá para medir cobertura e indícios de qualidade, mas não erro. O primeiro script trabalha nesse regime, e a vantagem é que roda sobre a saída de qualquer pessoa, sem exigir nada além de um `.txt` por PDF.

O segundo resolve a falta de gabarito com um truque: as páginas que já têm camada de texto nativo trazem o texto exato do documento. Rasterizando essas páginas como imagem e passando no OCR, dá para comparar o resultado com o texto que já se sabia correto. Sai erro de caractere e de palavra medidos sobre este corpus, sem transcrever nada à mão.

## Instalação

```bash
pip install pymupdf rapidfuzz
sudo apt install tesseract-ocr tesseract-ocr-por wbrazilian
```

O `rapidfuzz` é opcional, acelera a distância de edição. Sem ele o script usa uma implementação em Python puro, correta mas lenta. O `wbrazilian` instala a lista de palavras em `/usr/share/dict/brazilian`, usada na taxa de dicionário. Sem ela, essa métrica é pulada e as demais continuam valendo.

## Comparando soluções

```bash
python metricas_extracao.py \
    --solucao minha=../extracao_texto_peticoes/texto_peticoes \
    --solucao colega_a=/caminho/da/saida_dele \
    --solucao colega_b=/outro/caminho \
    --pdfs ../scrapping_processos_controle_concentrado/peticoes_processos_estruturantes
```

A única exigência para a saída de outra pessoa é que cada PDF vire um `.txt` de mesmo nome base. O resultado sai como tabela no terminal e como CSV.

Para o benchmark ser justo, todas as soluções têm que rodar sobre o **mesmo conjunto de PDFs**. Passe sempre a mesma pasta em `--pdfs`, que é o denominador da cobertura.

## O que cada métrica significa

**Cobertura.** Quantos PDFs viraram texto e quantas páginas isso representa. Existe para impedir a leitura ingênua das métricas de qualidade. Uma solução que descarta as páginas difíceis sobe na qualidade e cai aqui. Os dois blocos têm que ser lidos juntos.

**Volume.** Caracteres por página e tamanho médio do token. Um valor muito baixo indica texto perdido. Um tamanho médio de token fora do normal indica texto quebrado em fragmentos.

**Qualidade léxica.** Fração das palavras que existem no dicionário pt_BR. É o indicador mais sensível a erro de reconhecimento: OCR ruim inventa palavras que não existem. A taxa de ruído conta tokens impossíveis em português, como sequências sem vogal ou com letras repetidas.

Atenção à leitura do valor absoluto. Texto jurídico tem muito nome próprio, sigla, expressão em latim e número de lei, que não estão em dicionário comum. Por isso nem o texto nativo chega perto de 100%. O número isolado não diz muito.

**Qualidade por origem do texto.** É a parte que realmente mede o OCR, e só funciona se a solução gravar os marcadores de página. A taxa nas páginas nativas é o teto alcançável neste corpus, já que esse texto é exato por construção. A taxa nas páginas de OCR é o que se conseguiu. A diferença entre as duas, mostrada como defasagem, é o custo real do reconhecimento, livre do efeito do vocabulário jurídico. É esse número que deve ser comparado entre soluções, não a taxa bruta.

**Estrutura jurídica.** Fração dos documentos em que aparecem elementos que quase toda petição inicial tem: endereçamento ao STF, citação de artigo, citação de lei, menção à Constituição e formulação de pedido. Serve para pegar a falha silenciosa, quando a extração termina sem erro mas perdeu o corpo do documento. Valores muito abaixo de 90% merecem investigação.

**Desempenho.** Lido do log da extração, quando informado.

## Medindo o erro do OCR

```bash
# erro na configuração atual
python benchmark_ocr.py --paginas 40

# compara resoluções, para justificar a escolha de DPI
python benchmark_ocr.py --paginas 30 --dpi 150 --dpi 200 --dpi 300

# mostra o ganho do pacote de português contra o modelo de inglês
python benchmark_ocr.py --paginas 30 --idioma por --idioma eng
```

O resultado vem em duas tabelas, e ler só uma delas leva a conclusão errada.

**Sensível à ordem de leitura.** São as medidas padrão da área, ambas baseadas em distância de edição.

- **CER**, taxa de erro de caractere, é a distância de edição dividida pelo número de caracteres do gabarito.
- **WER**, taxa de erro de palavra, é a mesma ideia no nível de palavra.

**Insensível à ordem.** Compara os dois textos como sacola de palavras, medindo recall, precisão e F1. Ignora completamente onde cada palavra apareceu.

A segunda tabela existe por um motivo concreto descoberto neste corpus. A tarja de assinatura digital do STF é texto vertical na margem da página. O extrator nativo a insere no meio do fluxo do texto, e o OCR a coloca em outro lugar. Isso desloca blocos inteiros e faz a distância de edição disparar, mesmo com todas as palavras reconhecidas corretamente.

Numa medição de exemplo, as mesmas páginas deram CER de 10,7% e F1 de 97,7%. O reconhecimento estava quase perfeito. O CER media outra coisa.

| Combinação | Interpretação |
|---|---|
| CER alto e F1 alto | Ordem de leitura diferente, reconhecimento bom |
| CER alto e F1 baixo | Reconhecimento ruim de verdade |
| CER baixo e F1 alto | Tudo certo |

Para comparar soluções, o F1 é o número mais confiável neste corpus. O CER continua útil para comparar configurações da mesma solução, onde o efeito da ordem é constante.

Além da média são reportadas mediana e percentil 90. A mediana descreve a página típica, e o percentil 90 mostra o comportamento nas páginas ruins, que é onde as soluções costumam se diferenciar.

A amostragem é reprodutível pela semente, fixada em 42, e limitada a duas páginas por documento para não concentrar a medida em poucos arquivos. Use a mesma semente e a mesma quantidade de páginas em todas as soluções comparadas.

### Resultado medido nesta solução

Linha de base para comparação, sobre os 102 PDFs coletados. Primeiro o avaliador de saída:

| Métrica | Valor |
|---|---|
| Cobertura de arquivos e de páginas | 100% |
| Páginas processadas | 4.449 |
| Páginas vindas de OCR | 1.902, ou seja 42% |
| Falhas de OCR | 0 |
| Dicionário, páginas nativas | 86,61% |
| Dicionário, páginas de OCR | 87,08% |
| Ruído, páginas de OCR | 0,50% |
| Endereçamento ao STF presente | 97,06% dos documentos |
| Tempo de CPU por página | 1,63 s |

A taxa de dicionário nas páginas de OCR ficou acima da das páginas nativas. Não significa que o OCR seja melhor que o texto original. As páginas nativas concentram tabelas, notas de rodapé e cabeçalhos com siglas e números de processo, que não estão em dicionário comum. O que o número mostra é que o OCR não está introduzindo vocabulário inventado em escala relevante.

Depois o benchmark com gabarito, em 30 páginas, comparando resoluções:

| Configuração | CER médio | CER mediana | F1 médio | Segundos por página |
|---|---|---|---|---|
| Português a 200 DPI | 7,49% | 3,48% | 96,70% | 1,68 |
| Português a 300 DPI | 7,30% | 2,72% | 96,68% | 2,31 |

Duas leituras importantes.

A mediana do CER é bem menor que a média, 2,72% contra 7,30%. Poucas páginas ruins puxam a média para cima, e são justamente as afetadas pelo deslocamento da tarja de assinatura. A mediana descreve melhor a página típica.

As duas resoluções são indistinguíveis em qualidade, mas 200 DPI é 27% mais rápido. Ainda assim o padrão do projeto continua em 300 DPI, porque a medição foi feita sobre páginas nativas rasterizadas, que são limpas. Em digitalizações reais, com ruído e inclinação, a resolução maior tende a ajudar mais. Quem quiser trocar deve primeiro repetir a medida sobre páginas escaneadas de verdade, transcritas à mão.

### O limite honesto deste método

As páginas nativas rasterizadas são digitalizações limpas: sem ruído de papel, sem inclinação, sem mancha, sem sombra de encadernação. Digitalizações reais têm tudo isso. O erro medido aqui é, portanto, um **piso**, não uma previsão do erro nos escaneados verdadeiros.

Isso não invalida o uso. Para comparar configurações entre si, ou soluções entre si, o piso funciona bem, porque todas são medidas nas mesmas condições. O que não se pode fazer é anunciar o CER daqui como sendo o erro da extração sobre o corpus real.

Quem quiser a medida absoluta precisa transcrever à mão algumas páginas escaneadas de verdade e comparar com elas. Vinte páginas já dão uma estimativa utilizável.
