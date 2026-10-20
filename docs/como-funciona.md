# Como o JurisMatch funciona

Este documento explica o projeto para quem vai lê-lo, não rodá-lo. Não há código aqui.
Quem quiser executar o sistema encontra as instruções no README do repositório.

---

## 1. O problema

O Supremo Tribunal Federal julga ações de controle concentrado de constitucionalidade.
São processos em que se questiona uma lei em abstrato, sem um caso concreto por trás.
As principais são a ADI, ação direta de inconstitucionalidade, e a ADC, ação declaratória
de constitucionalidade.

Toda ação dessas começa com uma petição inicial. É nela que o autor expõe qual lei está
atacando, por quais razões, e o que pede. Esse é o documento mais informativo do processo
para quem quer entender o argumento jurídico.

O problema prático é o volume. Reunimos 97 petições, somando 4.536 páginas. Algumas
passam de 200 páginas. Encontrar qual delas discute um tema específico, lendo ou usando
busca por palavra, é inviável.

E a busca por palavra falha por um motivo mais profundo que o volume. Quem procura
"censura a jornais" não encontra a petição que escreveu "vedação à restrição prévia de
publicações". Os dois textos falam da mesma coisa e não compartilham nenhuma palavra.
Linguagem jurídica é cheia desse tipo de sinônimo.

O JurisMatch resolve isso. Você escreve uma pergunta em português comum e recebe uma
lista de petições ordenada por relevância. Cada uma vem com o trecho mais pertinente e
a página exata do PDF onde está.

---

## 2. Visão geral

O sistema tem cinco etapas, cada uma consumindo o resultado da anterior.

| Etapa | Entrada | Saída |
|---|---|---|
| 1. Coleta | Planilha de 906 processos do STF | 102 arquivos PDF |
| 2. Extração | PDFs | 4.536 páginas de texto |
| 3. Fragmentação | Texto | 8.278 trechos com metadados |
| 4. Indexação | Trechos | Índice de busca |
| 5. Busca | Pergunta em português | Ranking de petições |

As três primeiras etapas são preparação e rodam uma vez. A quinta é o uso do dia a dia.

---

## 3. Etapa 1: obter os documentos

O ponto de partida foi uma planilha exportada do portal do STF, com 906 processos de
controle concentrado e o link de cada um. A planilha traz metadados abundantes, como
relator, data de autuação e assunto, mas nenhum documento.

Baixar as petições exigiu percorrer o site processo por processo. Não existe interface
para download em lote.

### O obstáculo

O domínio do STF que hospeda os documentos é protegido por um firewall de aplicação
configurado para desafiar visitantes automatizados. Um programa que simplesmente peça o
arquivo recebe uma resposta vazia.

Para ser atendido, o visitante precisa de um cookie de autorização. E esse cookie só é
emitido depois que um navegador executa um script de verificação em JavaScript. Não é um
captcha, não exige pessoa nenhuma clicando. O que o teste verifica é se do outro lado
existe um navegador real, capaz de rodar aquele script.

### A solução

Em vez de pedir o arquivo diretamente, o coletor abre um navegador Chromium de verdade,
controlado por programa. O navegador resolve o desafio sozinho, porque é exatamente o que
o teste espera encontrar. Obtido o cookie, o download do PDF é feito reaproveitando a
mesma sessão.

O cookie expira no meio de uma sequência longa de downloads. Quando isso acontece, o
coletor recarrega a página para renová-lo e continua de onde parou.

### Resultado

Foram processadas as 100 primeiras linhas da planilha. Noventa e sete renderam a petição
inicial. Três não tinham peça eletrônica disponível ao público, todas em processos
anteriores a 2010.

O total de 102 arquivos é maior que o de petições porque quatro delas estão divididas em
partes no sistema do STF. A ADI 3494, por exemplo, vem em três arquivos.

---

## 4. Etapa 2: transformar os PDFs em texto

Aqui aparece a distinção mais importante do projeto, e ela reaparece no resultado da
busca. Existem dois tipos de PDF.

**PDF nativo.** Alguém escreveu a petição num editor de texto e exportou. As letras estão
guardadas no arquivo como letras. Extrair é só ler o que está lá, e a transcrição sai
exata, caractere por caractere.

**PDF digitalizado.** Alguém imprimiu a petição e passou no scanner. O arquivo contém uma
fotografia da folha. Não existe nenhuma letra dentro dele, apenas pixels.

Para o segundo caso é preciso reconhecimento óptico de caracteres, o OCR. O programa olha
a imagem e adivinha quais letras são aquelas formas. Adivinhar erra, e os erros aparecem:
acentos trocados, números confundidos, palavras inventadas a partir de manchas no papel.

### Quanto do corpus precisava de OCR

Medimos antes de decidir. O resultado contrariou a expectativa inicial.

| Tipo de página | Quantidade |
|---|---|
| Texto nativo | 2.630 |
| Digitalizada, sem texto | 1.902 |
| Vazia ou só assinatura | 4 |

Quase 42% das páginas não tinham camada de texto. Em documentos inteiros: 65 eram
totalmente nativos, 31 totalmente digitalizados e 6 mistos.

Duas conclusões vieram desses números.

A primeira é que não se pode usar apenas o leitor de texto, porque metade do corpus
ficaria em branco. A segunda é que não se pode usar apenas OCR, porque as páginas
nativas já têm o texto exato e passá-las por OCR introduziria erro onde não havia nenhum,
além de levar muito mais tempo.

### A decisão é por página

Como seis documentos misturam os dois tipos, a escolha não pode ser feita por arquivo.
A segunda parte da ADI 3494 tem 66 páginas nativas e 37 digitalizadas no mesmo PDF.

Então cada página é avaliada isoladamente. Se tem texto suficiente, o texto é lido direto.
Se não tem texto mas tem uma imagem cobrindo a folha, vai para o OCR. Se não tem nem uma
coisa nem outra, é página em branco ou de assinatura, e é ignorada.

Essa segunda condição é o detalhe que evita desperdício. Páginas de assinatura têm pouco
texto e nenhuma imagem grande. Sem checar a cobertura de imagem, o OCR rodaria nelas e
não devolveria nada.

### Um achado que vale registrar

A data do processo não prevê se ele é digitalizado. A digitalização se concentra em
processos antigos, mas a ADC 96 e a ADC 97, ambas de 2025, vieram inteiramente
escaneadas. Advogados ainda imprimem, assinam e digitalizam.

### O que fica registrado

Cada página do texto extraído carrega uma marca com o seu número e a sua origem, nativa
ou de OCR. Essa marca atravessa todo o resto do sistema e é o que permite, no final,
avisar o leitor sobre a confiabilidade de cada trecho.

---

## 5. Etapa 3: cortar o texto em trechos

### Por que cortar

Se cada petição fosse tratada como uma unidade só, dois problemas apareceriam.

O primeiro é de localização. O sistema diria que está na ADI 5613 e o leitor teria que
procurar em 60 páginas.

O segundo é mais sutil e diz respeito à etapa seguinte. Vamos representar cada texto por
um resumo numérico do seu assunto. Fazer isso com 200 páginas de uma vez produz uma
média sem sentido, porque a petição fala de legitimidade, de mérito e de pedido cautelar
ao mesmo tempo. Trechos menores têm assunto definido.

### Onde cortar

O corte não é a cada tanto de caracteres. É nas fronteiras naturais do documento.

A ordem de preferência é: títulos de seção primeiro, depois quebras de parágrafo. Só se um
parágrafo sozinho exceder o limite ele é dividido, e aí entre frases, nunca no meio de uma.

Cortar no meio de uma frase destruiria justamente o sentido que se quer capturar. É por
isso que o divisor de frases conhece abreviações jurídicas: ele sabe que o ponto em
"art. 5º" ou em "fls. 10" não encerra a frase.

Cada trecho tem como alvo 350 unidades de texto, algo próximo de meia página, com teto
em 480. O teto existe por uma razão técnica da etapa seguinte, explicada adiante.

### Limpeza

Antes de cortar, o texto passa por uma limpeza conservadora. São removidos números de
página soltos, carimbos de assinatura digital do STF, timbres de escritório que se
repetem em toda página e páginas de sumário com pontilhado.

Linhas quebradas no meio de frases são rejuntadas, inclusive desfazendo a hifenização de
fim de linha. Vários arquivos vinham com uma linha em branco entre todas as linhas, e
isso também é corrigido.

A limpeza descartou 4% das linhas. O número é baixo de propósito: na dúvida, o texto é
mantido, porque descartar conteúdo real é pior que carregar algum ruído.

### O cabeçalho de contexto

Cada trecho recebe uma linha colada no topo, identificando a petição e a seção de onde
veio, no formato "ADI 5613 | IV.3 A interpretação do art. 222".

Isso existe para resolver um erro típico em busca jurídica. Um parágrafo isolado não sabe
de qual processo é, e petições diferentes argumentam de maneira parecida. Sem o cabeçalho,
a busca traz o parágrafo certo da petição errada com frequência incômoda.

### Resultado

Saíram 8.278 trechos de 95 petições. A mediana é de 322 unidades de texto por trecho.

| Medida | Valor |
|---|---|
| Trechos | 8.278 |
| Petições representadas | 95 |
| Trechos por petição, mediana | 53 |
| Trechos na maior petição | 1.250 |
| Trechos vindos de OCR | 3.601 |

Cada trecho guarda: a petição de origem, a classe e o número da ação, o arquivo PDF, a
página inicial e final, se o texto é nativo ou de OCR, e a seção da petição.

São duas petições a menos que as 97 coletadas, pelo motivo explicado nas limitações.

---

## 6. Etapa 4: transformar texto em números

Esta é a ideia central do projeto.

### O que é um embedding

Um embedding é uma forma de representar um texto como uma lista de números. Aqui, 768
números por trecho.

A analogia útil é a de coordenadas. Um ponto no mapa tem duas, latitude e longitude.
Cada trecho de petição aqui é um ponto com 768 coordenadas. Não é possível desenhar isso,
mas a matemática funciona do mesmo jeito: dá para medir a distância entre dois pontos.

A propriedade que torna tudo isso útil é esta: o modelo que gera os números foi treinado
de modo que textos com significado próximo caiam perto um do outro, e textos sobre
assuntos diferentes caiam longe.

É isso que resolve o problema do sinônimo. "Censura a jornais" e "vedação à restrição
prévia de publicações" caem vizinhos no espaço de coordenadas, embora não compartilhem
palavra alguma.

### O modelo escolhido

Foi usado um modelo multilíngue que entende português, com licença livre e tamanho
suficiente para rodar num computador comum, sem placa de vídeo.

Ele lê no máximo 512 unidades de texto por vez e corta o excedente. É essa a razão do
teto de 480 na etapa anterior: garantir que nenhum trecho perca conteúdo na representação.

O modelo tem uma exigência peculiar. É preciso avisar se o texto submetido é uma pergunta
ou um documento, com um prefixo. Ele foi treinado assim, e omitir o prefixo degrada o
resultado.

### O custo

Calcular os 8.278 trechos levou 45 minutos no processador. Desses, apenas 7.899 vetores
foram efetivamente calculados, porque 379 trechos são idênticos entre si e aproveitam o
mesmo resultado.

Esse cálculo roda uma vez. Depois disso, cada busca leva milésimos de segundo.

### O índice

Com todo trecho virado em ponto, buscar significa achar quais pontos estão mais perto do
ponto da pergunta. Essa operação precisa de uma estrutura que a faça rápido, e é o que o
índice é.

Foi escolhida a versão exata, que compara a pergunta com todos os 8.278 trechos, em vez
da aproximada. Nessa escala a exata já responde instantaneamente, e ela tem a vantagem de
devolver sempre a mesma resposta para a mesma pergunta.

---

## 7. Etapa 5: a busca

### Por que dois sistemas

A busca por significado tem um ponto cego: números e códigos exatos. Para o modelo,
"Lei 11.101/2005" e "Lei 11.101/2006" significam praticamente a mesma coisa. Para um
jurista, não.

Por isso roda em paralelo um segundo sistema, de busca por palavra, à moda antiga,
contando ocorrências e levando em conta a raridade de cada termo. Ele é ruim em sinônimo
e preciso em termo exato. Os dois se complementam.

Esse segundo sistema foi configurado para português, ignorando palavras muito comuns e
reduzindo cada palavra ao seu radical, para que "recuperação" e "recuperar" sejam tratadas
como a mesma coisa.

O usuário pode escolher rodar só um dos dois, mas o padrão é usar os dois.

### Como os dois são combinados

Há um problema de escala. Um sistema devolve notas entre zero e um, o outro devolve
valores que passam de dez. Somar seria comparar grandezas diferentes.

A solução adotada descarta as notas e usa apenas as posições. Se um resultado ficou
em primeiro num sistema e em terceiro no outro, é isso que conta. Cada sistema contribui
com um valor que decresce conforme a posição, e os valores são somados.

A vantagem é não precisar calibrar peso nenhum entre os dois sistemas. O custo é perder a
informação de intensidade, e isso tem uma consequência prática explicada adiante.

### De trechos para petições

A busca encontra trechos, mas o usuário quer petições. A regra adotada é que cada
petição vale o seu melhor trecho, não a média dos seus trechos.

A escolha é deliberada. Se fosse média, uma petição de 200 páginas com um parágrafo
perfeito e trezentos irrelevantes afundaria no ranking. Com a regra do melhor trecho,
petições curtas e longas competem em igualdade.

Há um ganho adicional. O trecho vencedor é exatamente o que deve ser exibido ao usuário, e
ele já sabe a sua página no PDF.

---

## 8. Como ler um resultado

Cada linha da resposta traz a classe e o número da ação, uma nota, o arquivo PDF, a
página, uma marca de origem, a seção da petição e o início do trecho.

### A marca de origem

Diz se aquele trecho veio de texto nativo ou de OCR.

| Marca | O que significa | O que fazer |
|---|---|---|
| nativo | Transcrição exata do PDF | Pode citar literalmente |
| ocr | Texto adivinhado de uma imagem | Conferir no PDF antes de citar |
| misto | O trecho atravessa páginas dos dois tipos | Mesmo cuidado do OCR |

Essa marca é um aviso de confiabilidade, não de relevância. Um trecho de OCR pode ser o
mais pertinente da busca e ainda assim ter erros de transcrição. Serve para localizar o
argumento, e a citação literal deve sair do PDF.

### A nota

A nota indica posição, não qualidade. É o ponto mais fácil de interpretar errado.

Ela é calculada a partir do lugar que o resultado ocupou em cada um dos dois sistemas.
Isso significa que ela tem um valor máximo fixo, alcançado por quem ficou em primeiro
lugar nos dois.

A consequência importante: a nota não sabe se o resultado é bom. Quem fica em primeiro
recebe o valor máximo sempre, mesmo que seja a melhor opção de um conjunto ruim. Se a
pergunta tratar de um tema que não existe em nenhuma das 95 petições, o primeiro colocado
ainda aparecerá com nota máxima.

Além disso, as diferenças entre posições vizinhas são pequenas por construção, de cerca de
1,6% entre o primeiro e o segundo. Notas próximas significam que o sistema não está
seguro da ordem, e vale olhar os primeiros resultados, não apenas o primeiro.

Para julgar se o resultado presta, o indicador é o trecho. Leia o texto, não o número.

### A página

A página se refere ao arquivo PDF indicado na mesma linha, e não à petição como um todo.
Isso importa nas quatro petições divididas em partes, onde a numeração recomeça em cada
arquivo. Dizer "página 19 da ADI 2945" é ambíguo sem indicar de qual parte.

---

## 9. Como escrever uma boa pergunta

Isso muda a qualidade do resultado mais que qualquer parâmetro do sistema, e é
contraintuitivo para quem está acostumado com buscadores da web.

**Escreva uma frase inteira, não palavras soltas.** O modelo compara o significado da frase
como um todo. "Participação de capital estrangeiro em empresas jornalísticas" funciona
muito melhor que "capital estrangeiro".

**Descreva o problema jurídico, não o resultado desejado.** Em vez de pedir petições sobre
o artigo 222, descreva o limite à participação de estrangeiros na propriedade de empresas
de comunicação.

**Para número de lei ou de artigo, use o modo de busca por palavra.** O sistema de
significado confunde números próximos, e o lexical não.

---

## 10. O que o sistema não faz

Limitações conhecidas e aceitas nesta versão.

**Três petições estão fora do índice.** As ADI 4271, ADI 4376 e ADI 4393 são digitalizadas,
mas foram extraídas sem OCR na etapa 2. O único texto que sobrou nelas é o carimbo de
assinatura digital, e o corpo da petição se perdeu. São 263 páginas que precisam ser
reprocessadas. É por isso que o índice tem 95 petições e não 97.

**Anexos digitalizados entram junto.** Leis, pareceres e procurações anexados a algumas
petições geram centenas de trechos com OCR de baixa qualidade. A regra do melhor trecho
impede que dominem o ranking, mas eles estão lá e ocasionalmente aparecem.

**A identificação de seções é aproximada.** Apenas títulos numerados são reconhecidos, e
16% dos trechos ficam sem seção identificada.

**Notas de rodapé não são separadas do corpo.** Elas permanecem no parágrafo ou viram
parágrafos próprios, misturando referência bibliográfica com argumento.

**Não há avaliação quantitativa da qualidade da busca.** A validação feita foi qualitativa,
com quatro perguntas de resposta conhecida, todas respondidas corretamente. Medir recall e
precisão exigiria um conjunto de perguntas com respostas rotuladas à mão, o que é trabalho
de uma etapa seguinte.

**O corpus é parcial.** Foram processadas 100 das 906 linhas da planilha.

---

## 11. Números do projeto

| Medida | Valor |
|---|---|
| Processos na planilha de origem | 906 |
| Processos coletados | 100 |
| Petições obtidas | 97, sendo 75 ADI e 20 ADC |
| Arquivos PDF | 102 |
| Páginas de texto | 4.536 |
| Páginas com texto nativo | 2.630 |
| Páginas reconhecidas por OCR | 1.902 |
| Trechos indexados | 8.278 |
| Petições no índice | 95 |
| Coordenadas por trecho | 768 |
| Tempo para calcular os embeddings | 45 minutos |
| Tempo de uma busca | 22 milésimos de segundo |

---

## 12. Decisões de desenho, em resumo

Para quem quiser o racional técnico condensado.

| Decisão | Escolha | Razão |
|---|---|---|
| Onde cortar o texto | Seção, depois parágrafo, depois frase | Fronteiras naturais preservam sentido melhor que corte fixo |
| Tamanho do trecho | Alvo de 350, teto de 480 | O modelo lê no máximo 512 e corta o excedente |
| Contexto no trecho | Cabeçalho com petição e seção | Reduz o erro de trazer o trecho certo da petição errada |
| Tipo de índice | Exato, não aproximado | Nessa escala o exato já é instantâneo e é determinístico |
| Busca | Significado mais palavra exata | O significado falha em números de lei |
| Combinação | Por posição, não por nota | As notas dos dois sistemas têm escalas incompatíveis |
| Trecho para petição | Melhor trecho, não média | Faz petições curtas e longas competirem em igualdade |
| OCR | Por página, não por documento | Seis documentos misturam páginas nativas e digitalizadas |

O estudo que fundamenta essas escolhas está na pasta de pesquisa, e o plano de
implementação na pasta de planos, ambas dentro de `docs/`.
