// Cliente da API (contrato em docs/superpowers/plans/2026-11-10-frontend-pwa.md).

export class ErroApi extends Error {
  /** tipo: "indice" (503), "validacao" (422), "servidor", "rede" */
  constructor(tipo, mensagem, status = 0) {
    super(mensagem);
    this.tipo = tipo;
    this.status = status;
  }
}

async function detalhe(resp) {
  try {
    const corpo = await resp.json();
    if (typeof corpo.detail === "string") return corpo.detail;
    if (Array.isArray(corpo.detail) && corpo.detail[0]?.msg) return String(corpo.detail[0].msg);
  } catch {
    /* corpo não é JSON */
  }
  return `Erro ${resp.status}`;
}

export async function status({ signal } = {}) {
  const resp = await fetch("/api/status", { signal, cache: "no-store" });
  if (!resp.ok) throw new ErroApi("servidor", await detalhe(resp), resp.status);
  return resp.json();
}

export async function buscar(corpo, { signal } = {}) {
  let resp;
  try {
    resp = await fetch("/api/buscar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
      signal,
      cache: "no-store",
    });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new ErroApi("rede", "Não foi possível falar com o servidor.");
  }
  if (resp.status === 503) throw new ErroApi("indice", await detalhe(resp), 503);
  if (resp.status === 422) throw new ErroApi("validacao", await detalhe(resp), 422);
  if (!resp.ok) throw new ErroApi("servidor", await detalhe(resp), resp.status);
  return resp.json();
}

/** Página oficial do processo: só https no portal do STF (resposta antiga sem o campo, null ou outro domínio = sem link). */
export function urlStfSegura(url) {
  if (typeof url !== "string" || !url.startsWith("https://portal.stf.jus.br/")) return null;
  try {
    const u = new URL(url);
    return u.protocol === "https:" && u.hostname === "portal.stf.jus.br" ? u.href : null;
  } catch {
    return null;
  }
}

/** Só aceita link de PDF servido pela própria API (evita javascript: ou domínio externo vindo do JSON). */
export function urlPdfSegura(url) {
  if (typeof url !== "string") return null;
  return /^\/api\/pdf\/[A-Za-z0-9_.-]+\.pdf(#page=\d+)?$/.test(url) ? url : null;
}
