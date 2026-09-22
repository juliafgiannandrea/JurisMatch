# JurisMatch

Projeto sobre as petições iniciais dos processos de controle concentrado de constitucionalidade do STF (ADI, ADPF, ADC e ADO).

## Etapas

1. **Coleta das petições (scraping do STF)** — [`scrapping_processos_controle_concentrado/`](scrapping_processos_controle_concentrado/README.md)
   Script em Python + Playwright que lê a planilha de processos do STF, contorna o desafio JavaScript do AWS WAF do site e baixa os PDFs das petições iniciais.
