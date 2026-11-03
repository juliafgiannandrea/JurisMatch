# Pontos fortes
A decisão é por página, não por documento. Os 6 PDFs mistos seriam extraídos pela metade se a decisão fosse por documento.
O critério de OCR tem duas condições (pouco texto e imagem grande). Isso evita gastar OCR em página de assinatura ou em branco, e ainda separa "vazia" de "falhou" no log.

As decisões se apoiam em dados. A docstring registra a calibração (58/42%, os casos ADC 96/98, o benchmark de get_image_info). Quem for manter o script entende o porquê de cada escolha, não só o quê.

O paralelismo está bem feito. Usa ProcessPoolExecutor, e OMP_THREAD_LIMIT=1 evita que cada tesseract abra várias threads e dispute CPU com os outros processos. É um detalhe que muita gente esquece.

Não usa arquivos temporários no OCR. O PNG vai pelo stdin e volta pelo stdout.

Há rastreabilidade. Os marcadores [[pagina N | metodo]] e o CSV por arquivo permitem auditar depois qual página veio de OCR.
A usabilidade é boa. O tesseract é verificado antes de começar, há --limite para testar e --sem-ocr para uma passada rápida, e o CSV sai com ; e utf-8-sig para abrir direto no Excel em PT-BR.

# Pontos fracos (do mais grave ao menos)
--sem-ocr impede o OCR nas execuções seguintes. A passada rápida grava os .txt com as páginas marcadas como pendente. Na execução completa seguinte, PULAR_JA_EXTRAIDOS pula esses arquivos, e o OCR nunca roda sem --forcar. O fluxo que a própria docstring sugere (rápido primeiro, completo depois) cai nesse problema. Duas soluções possíveis: gravar a saída do --sem-ocr em outra pasta, ou só pular arquivos cujo .txt não contenha | pendente]].
Arquivos com falha não são reprocessados. Um arquivo ok_com_falhas já tem .txt, então as páginas cujo OCR falhou nunca são tentadas de novo. Além disso, write_text não é atômico. Se o processo morrer no meio da gravação, fica um .txt truncado que também é pulado. O ideal é gravar em .txt.tmp e fazer os.replace no final.
Carimbos podem esconder páginas digitalizadas. O critério chars >= 100 é absoluto. Uma página digitalizada que recebeu uma tarja de texto nativo (carimbo de assinatura digital, "documento pode ser acessado em... código XXXX", número de folha) passa facilmente de 100 caracteres. Ela é classificada como nativo e o corpo da petição se perde. Vale conferir nos PDFs do e-STF. Uma correção é, quando a cobertura de imagem for alta, exigir bem mais texto (por exemplo, mais de 800 caracteres) antes de confiar no texto nativo.
Não há checagem de qualidade do texto nativo. Uma camada de OCR antiga e ruim, ou fontes sem mapeamento Unicode (que viram lixo como ÿþ§...), passam no critério de contagem. Uma heurística simples ajuda: a proporção de letras e dígitos sobre o total, ou a fração de palavras com vogal. Abaixo de um limiar, a página vai para OCR.
O parâmetro flags= substitui os flags padrão do PyMuPDF, em vez de somar. Passando só TEXT_DEHYPHENATE, perde-se o TEXT_MEDIABOX_CLIP, e texto fora da área visível da página pode entrar na extração. O mais seguro é flags=pymupdf.TEXTFLAGS_TEXT | pymupdf.TEXT_DEHYPHENATE.
A normalização do espaço não separável provavelmente não faz nada. A linha texto.replace(" ", " ") parece ter perdido o NBSP ao ser colada, e o regex [ \t]+ não o captura. Use o escape explícito: texto.replace("\u00a0", " ").
Páginas digitalizadas de lado viram lixo. O --psm 3 não corrige orientação. Se houver páginas deitadas, dá para rodar --psm 0 (OSD) antes, ou rotacionar quando o OCR devolver pouco texto.
O cálculo de cobertura de imagem pode errar. Ele soma bounding boxes sem fazer a interseção com pagina.rect e sem descontar sobreposição. Imagens que ultrapassam a página ou que se sobrepõem inflam a cobertura. O min(..., 1.0) esconde isso no total, mas não em casos intermediários, como fundo mais logo.
O log tem algumas arestas:
--forcar --limite 5 sobrescreve o CSV inteiro com só 5 linhas, e o histórico se perde.
A confiança do OCR não é registrada, então não há como identificar depois os documentos com OCR ruim. O tesseract dá isso via tsv.
chars no log conta espaços, enquanto o critério por página não conta. As duas métricas não são comparáveis.
Detalhes menores:
O except (subprocess.TimeoutExpired, RuntimeError, Exception) é redundante, porque Exception já cobre os outros dois.
glob("*.pdf") ignora arquivos .PDF.
Os caminhos padrão são relativos ao diretório de onde o script é executado, não à pasta do script.
Se um worker morrer por segfault no MuPDF, o ProcessPoolExecutor quebra e todos os futuros restantes aparecem como erro.