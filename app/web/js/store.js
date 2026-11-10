// Persistência local (localStorage). Tudo tolerante a falha: modo privado ou cota cheia não quebram o app.

const CHAVES = {
  opcoes: "jm.opcoes.v1",
  historico: "jm.historico.v1",
  ultima: "jm.ultima.v1",
  dicaIos: "jm.dica-ios.v1",
};
const MAX_HISTORICO = 10;

function ler(chave, padrao) {
  try {
    const bruto = localStorage.getItem(chave);
    return bruto === null ? padrao : JSON.parse(bruto);
  } catch {
    return padrao;
  }
}

function gravar(chave, valor) {
  try {
    localStorage.setItem(chave, JSON.stringify(valor));
  } catch {
    /* sem armazenamento: segue sem lembrar */
  }
}

export const OPCOES_PADRAO = { k: 5, modo: "hibrido", classe: null, rerank: true, limiar: 0.8 };
const MODOS = ["hibrido", "denso", "lexical"];
const CLASSES = ["ADI", "ADC", "ADO", "ADPF"];

/** Valida e completa as opções (o localStorage pode ter lixo de versões antigas). */
export function normalizarOpcoes(o = {}) {
  const k = Number.parseInt(o.k, 10);
  const limiar = Number(o.limiar);
  return {
    k: Number.isFinite(k) ? Math.min(20, Math.max(1, k)) : OPCOES_PADRAO.k,
    modo: MODOS.includes(o.modo) ? o.modo : OPCOES_PADRAO.modo,
    classe: CLASSES.includes(o.classe) ? o.classe : null,
    rerank: typeof o.rerank === "boolean" ? o.rerank : OPCOES_PADRAO.rerank,
    limiar: Number.isFinite(limiar) ? Math.min(1, Math.max(0.5, Math.round(limiar * 20) / 20)) : OPCOES_PADRAO.limiar,
  };
}

export const store = {
  opcoes: () => normalizarOpcoes(ler(CHAVES.opcoes, OPCOES_PADRAO)),
  salvarOpcoes: (o) => gravar(CHAVES.opcoes, normalizarOpcoes(o)),

  historico() {
    const lista = ler(CHAVES.historico, []);
    return Array.isArray(lista) ? lista.filter((h) => h && typeof h.consulta === "string") : [];
  },
  registrarBusca(consulta, opcoes) {
    const resto = this.historico().filter((h) => h.consulta !== consulta);
    gravar(CHAVES.historico, [{ consulta, opcoes, quando: Date.now() }, ...resto].slice(0, MAX_HISTORICO));
  },
  removerDoHistorico(consulta) {
    gravar(CHAVES.historico, this.historico().filter((h) => h.consulta !== consulta));
  },
  limparHistorico: () => gravar(CHAVES.historico, []),

  ultima: () => ler(CHAVES.ultima, null),
  salvarUltima: (resposta, opcoes) => gravar(CHAVES.ultima, { resposta, opcoes, quando: Date.now() }),

  dicaIosDispensada: () => ler(CHAVES.dicaIos, false),
  dispensarDicaIos: () => gravar(CHAVES.dicaIos, true),
};
