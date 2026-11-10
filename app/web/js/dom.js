// Helpers de DOM. Todo texto vindo da API entra como textContent ou nó de texto, nunca via innerHTML.

/** Cria um elemento: el("p", {class: "x"}, "texto", outroNo). Atributos começando com "on" viram listeners. */
export function el(tag, attrs = {}, ...filhos) {
  const no = document.createElement(tag);
  for (const [nome, valor] of Object.entries(attrs)) {
    if (valor === null || valor === undefined || valor === false) continue;
    if (nome.startsWith("on") && typeof valor === "function") no.addEventListener(nome.slice(2), valor);
    else if (nome === "class") no.className = valor;
    else no.setAttribute(nome, valor === true ? "" : String(valor));
  }
  for (const f of filhos.flat()) {
    if (f === null || f === undefined || f === false) continue;
    no.append(f instanceof Node ? f : document.createTextNode(String(f)));
  }
  return no;
}

const SVG = "http://www.w3.org/2000/svg";

/** Ícone do sprite inline (<symbol id="i-...">). */
export function icone(nome) {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", "ic");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVG, "use");
  use.setAttribute("href", `#i-${nome}`);
  svg.append(use);
  return svg;
}

const PALAVRAS_VAZIAS = new Set(
  ("a o as os de da do das dos e em no na nos nas um uma uns umas para por pela pelo pelas pelos com sem " +
   "que se ao aos ou sobre entre como mais menos nao sua seu suas seus lei art").split(" ")
);

function semAcento(s) {
  return s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

/** Termos da consulta usados para grifar o trecho (sem acento, minúsculos, sem palavras vazias). */
export function termosDaConsulta(consulta = "") {
  if (!consulta) return [];
  const termos = semAcento(String(consulta))
    .split(/[^\p{L}\p{N}]+/u)
    .filter((t) => t.length >= 3 && !PALAVRAS_VAZIAS.has(t));
  return [...new Set(termos)].sort((a, b) => b.length - a.length);
}

/**
 * Devolve um DocumentFragment com o texto e os termos grifados em <mark>.
 * Casa ignorando acento e caixa, no início de palavra (imprensa casa "Imprensa" e "imprensas").
 */
export function grifar(texto, termos) {
  const frag = document.createDocumentFragment();
  if (!texto) return frag;
  if (!termos.length) { frag.append(texto); return frag; }

  // Texto normalizado com mapa de posições de volta para o original.
  let norm = "";
  const mapa = [];
  for (let i = 0; i < texto.length; i++) {
    const n = semAcento(texto[i]);
    for (let j = 0; j < n.length; j++) { norm += n[j]; mapa.push(i); }
  }
  const escapados = termos.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const re = new RegExp(`(?<![\\p{L}\\p{N}])(?:${escapados.join("|")})[\\p{L}\\p{N}]*`, "gu");

  let cursor = 0;
  for (const m of norm.matchAll(re)) {
    const rawIni = mapa[m.index];
    const rawFim = mapa[m.index + m[0].length - 1] + 1;
    const ini = Math.max(cursor, rawIni);
    const fim = Math.max(ini, rawFim);
    if (ini > cursor) frag.append(texto.slice(cursor, ini));
    if (fim > ini) frag.append(el("mark", {}, texto.slice(ini, fim)));
    cursor = Math.max(cursor, fim);
  }
  if (cursor < texto.length) frag.append(texto.slice(cursor));
  return frag;
}

const fmtPct = new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 0 });
const fmtInt = new Intl.NumberFormat("pt-BR");

export const formatar = {
  pct: (v) => fmtPct.format(v),
  int: (v) => fmtInt.format(v),
  dec: (v, casas) => new Intl.NumberFormat("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }).format(v),
  quando(ts) {
    const seg = Math.round((Date.now() - ts) / 1000);
    if (seg < 60) return "agora";
    const min = Math.round(seg / 60);
    if (min < 60) return `há ${min} min`;
    const h = Math.round(min / 60);
    if (h < 24) return `há ${h} h`;
    const d = Math.round(h / 24);
    if (d < 7) return d === 1 ? "ontem" : `há ${d} dias`;
    return new Date(ts).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
  },
};
