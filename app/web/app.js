// JurisMatch PWA: interface de busca. Módulos em /js; sem build.
import { el, icone, grifar, termosDaConsulta, formatar } from "./js/dom.js";
import { store, normalizarOpcoes } from "./js/store.js";
import * as api from "./js/api.js";

const $ = (sel) => document.querySelector(sel);

const EXEMPLOS = [
  "liberdade de imprensa e capital estrangeiro",
  "vaquejada e maus-tratos a animais",
  "guerra fiscal de ICMS e benefícios sem convênio",
  "piso salarial nacional do magistério",
  "foro por prerrogativa de função em constituição estadual",
  "cotas raciais em universidades públicas",
];

const AJUDA_MODO = {
  hibrido: "Combina significado e palavras exatas (BM25).",
  denso: "Procura pelo sentido, mesmo que o texto use outras palavras.",
  lexical: "Só palavras exatas (BM25). Não calcula similaridade.",
};
const NOME_MODO = { hibrido: "híbrido", denso: "só semântico", lexical: "só palavras" };
const LIMITE_TRECHO = 650; // caracteres a partir dos quais o trecho começa recolhido

const ui = {
  form: $("#form-busca"),
  consulta: $("#consulta"),
  botaoBuscar: $("#btn-buscar"),
  painel: $("#painel"),
  opcoes: $("#opcoes"),
  fundo: $("#fundo-folha"),
  botaoOpcoes: $("#btn-opcoes"),
  resumoOpcoes: $("#resumo-opcoes"),
  k: $("#opt-k"),
  saidaK: $("#saida-k"),
  classe: $("#opt-classe"),
  rerank: $("#opt-rerank"),
  limiar: $("#opt-limiar"),
  saidaLimiar: $("#saida-limiar"),
  campoLimiar: $("#campo-limiar"),
  ajudaModo: $("#ajuda-modo"),
  avisoRede: $("#aviso-rede"),
  contagem: $("#contagem"),
  tplCartao: $("#tpl-cartao"),
};

const estado = {
  opcoes: store.opcoes(),
  status: null, // resposta de /api/status (null se ainda não chegou ou falhou)
  busca: null, // { controlador, timer }
};

/* ------------------------------------------------------------------ opções */

function lerOpcoesDoFormulario() {
  return normalizarOpcoes({
    k: ui.k.value,
    modo: document.querySelector('input[name="modo"]:checked')?.value,
    classe: ui.classe.value || null,
    rerank: ui.rerank.checked,
    limiar: ui.limiar.value,
  });
}

function aplicarOpcoesNoFormulario(o) {
  ui.k.value = o.k;
  const radio = document.querySelector(`input[name="modo"][value="${o.modo}"]`);
  if (radio) radio.checked = true;
  ui.classe.value = o.classe ?? "";
  ui.rerank.checked = o.rerank;
  ui.limiar.value = o.limiar;
  atualizarRotulosOpcoes(o);
}

function atualizarRotulosOpcoes(o) {
  ui.saidaK.textContent = o.k;
  ui.saidaLimiar.textContent = formatar.pct(o.limiar);
  ui.limiar.disabled = !o.rerank;
  ui.campoLimiar.classList.toggle("campo--off", !o.rerank);
  ui.ajudaModo.textContent = AJUDA_MODO[o.modo];
  const partes = [
    `${o.k} ${o.k === 1 ? "petição" : "petições"}`,
    NOME_MODO[o.modo],
    o.classe ?? null,
    o.rerank ? `reranker ${formatar.pct(o.limiar)}` : "sem reranker",
  ].filter(Boolean);
  ui.resumoOpcoes.textContent = partes.join(" · ");
}

function aoMudarOpcao() {
  estado.opcoes = lerOpcoesDoFormulario();
  atualizarRotulosOpcoes(estado.opcoes);
  store.salvarOpcoes(estado.opcoes);
}

/* Folha inferior (celular) */
const ehDesktop = window.matchMedia("(min-width: 900px)");

function abrirFolha() {
  ui.opcoes.classList.add("aberta");
  ui.fundo.hidden = false;
  ui.botaoOpcoes.setAttribute("aria-expanded", "true");
  ui.opcoes.setAttribute("role", "dialog");
  ui.opcoes.setAttribute("aria-modal", "true");
  requestAnimationFrame(() => ui.k.focus({ preventScroll: true }));
}

function fecharFolha({ devolverFoco = true } = {}) {
  if (!ui.opcoes.classList.contains("aberta")) return;
  ui.opcoes.classList.remove("aberta");
  ui.fundo.hidden = true;
  ui.botaoOpcoes.setAttribute("aria-expanded", "false");
  ui.opcoes.removeAttribute("role");
  ui.opcoes.removeAttribute("aria-modal");
  if (devolverFoco) ui.botaoOpcoes.focus();
}

/* ------------------------------------------------------------------ telas */

function mostrar(...nos) {
  ui.painel.replaceChildren(...nos.filter((n) => n instanceof Node)); // ignora false/0 de "cond && el(...)"
}

function telaInicio() {
  const historico = store.historico();
  const blocos = [];

  if (historico.length) {
    const lista = el("ul", { class: "historico" },
      historico.map((h) =>
        el("li", {},
          el("button", {
            type: "button", class: "historico__item",
            onclick: () => buscar(h.consulta, normalizarOpcoes(h.opcoes)),
          },
            icone("relogio"),
            el("span", { class: "historico__texto" }, h.consulta),
            el("span", { class: "historico__quando" }, formatar.quando(h.quando)),
          ),
          el("button", {
            type: "button", class: "botao-icone", "aria-label": `Apagar "${h.consulta}" do histórico`,
            onclick: () => { store.removerDoHistorico(h.consulta); telaInicio(); },
          }, icone("fechar")),
        )
      )
    );
    blocos.push(el("section", { "aria-labelledby": "t-hist" },
      el("div", { class: "historico__cabeca" },
        el("h2", { class: "secao-titulo", id: "t-hist" }, "Buscas recentes"),
        el("button", { type: "button", class: "link-botao", onclick: () => { store.limparHistorico(); telaInicio(); } }, "Limpar"),
      ),
      lista,
    ));
  }

  blocos.push(el("section", { "aria-labelledby": "t-ex" },
    el("h2", { class: "secao-titulo", id: "t-ex" }, historico.length ? "Ou experimente" : "Experimente"),
    el("ul", { class: "exemplos" },
      EXEMPLOS.map((ex) => el("li", {}, el("button", { type: "button", class: "exemplo", onclick: () => buscar(ex) }, ex)))
    ),
  ));

  blocos.push(el("section", { class: "sobre" },
    el("p", {}, "Escreva a tese ou o tema com as suas palavras. O JurisMatch procura nos trechos das petições iniciais e devolve as que mais se aproximam, com a página onde o trecho está."),
  ));

  mostrar(el("div", { class: "inicio" }, blocos));
}

function telaIndiceAusente() {
  mostrar(el("div", { class: "estado bloco bloco--aviso" },
    el("h2", { class: "estado__titulo" }, "O índice de busca ainda não foi montado"),
    el("p", { class: "estado__texto" },
      "O servidor está no ar, mas não encontrou os arquivos do índice na pasta ", el("code", {}, "vectorstore/"),
      ". Sem eles não dá para buscar."),
    el("p", { class: "estado__texto" }, "Na raiz do projeto, rode ", el("code", {}, "python -m jurismatch.indexar"),
      " e depois verifique de novo."),
    el("div", { class: "estado__acoes" },
      el("button", { type: "button", class: "botao botao--fantasma", onclick: verificarIndice }, "Verificar de novo"),
    ),
  ));
}

async function verificarIndice() {
  await carregarStatus();
  if (estado.status?.indice_pronto) {
    const q = ui.consulta.value.trim();
    q ? buscar(q) : telaInicio();
  } else if (estado.status) {
    telaIndiceAusente();
    toast("O índice continua ausente.");
  }
}

function telaErro(titulo, texto, { tentar = true } = {}) {
  mostrar(el("div", { class: "estado estado--erro", role: "alert" },
    el("h2", { class: "estado__titulo" }, titulo),
    el("p", { class: "estado__texto" }, texto),
    tentar && el("div", { class: "estado__acoes" },
      el("button", { type: "button", class: "botao botao--fantasma", onclick: () => ui.form.requestSubmit() }, "Tentar de novo"),
    ),
  ));
}

function telaOfflineSemDados() {
  mostrar(el("div", { class: "estado" },
    el("h2", { class: "estado__titulo" }, "Sem conexão"),
    el("p", { class: "estado__texto" }, "A busca precisa do servidor. Assim que a conexão voltar, é só buscar de novo."),
  ));
}

function telaCarregando(opcoes) {
  const tempo = el("span", { class: "carregando__tempo" }, "0 s");
  const dicas = [];
  if (estado.status && !estado.status.buscador_carregado) {
    dicas.push("A primeira busca carrega o índice e os modelos na memória e pode levar mais de um minuto.");
  }
  if (opcoes.rerank) dicas.push("Com o reranker ligado, cada consulta leva uns 40 s em CPU.");

  mostrar(el("div", { class: "carregando" },
    el("span", { class: "carregando__marca", "aria-hidden": "true" }),
    el("div", { class: "estado" },
      el("p", { class: "estado__titulo" }, "Buscando… ", tempo),
      dicas.map((d) => el("p", { class: "estado__texto" }, d)),
      el("div", { class: "estado__acoes" },
        el("button", { type: "button", class: "botao botao--fantasma", onclick: cancelarBusca }, "Cancelar"),
      ),
    ),
  ));
  return tempo;
}

function telaVazia(resposta) {
  const texto = resposta.rerank
    ? `Nenhum resultado significativo: nenhuma petição atingiu relevância de ${formatar.pct(resposta.limiar)}. Reformule a consulta ou reduza a relevância mínima.`
    : "Nenhum resultado: nenhum trecho tem relação com a consulta.";
  const acoes = [];
  if (resposta.rerank && resposta.limiar > 0.5) {
    const novo = Math.max(0.5, Math.round((resposta.limiar - 0.2) * 20) / 20);
    acoes.push(el("button", {
      type: "button", class: "botao botao--fantasma",
      onclick: () => {
        aplicarOpcoesNoFormulario({ ...estado.opcoes, limiar: novo });
        aoMudarOpcao();
        buscar(resposta.consulta);
      },
    }, `Buscar com mínimo de ${formatar.pct(novo)}`));
  }
  mostrar(el("div", { class: "estado bloco" },
    el("h2", { class: "estado__titulo" }, "Nada encontrado"),
    el("p", { class: "estado__texto" }, texto),
    acoes.length && el("div", { class: "estado__acoes" }, acoes),
  ));
}

function telaResultados(resposta, { offlineDesde = null } = {}) {
  const resultados = Array.isArray(resposta.resultados) ? resposta.resultados : [];
  if (!resultados.length) return telaVazia(resposta);

  const termos = termosDaConsulta(resposta.consulta ?? "");
  const n = resultados.length;
  const meta = offlineDesde
    ? `salva ${formatar.quando(offlineDesde)}`
    : [
        typeof resposta.tempo_ms === "number" ? tempoLegivel(resposta.tempo_ms) : null,
        resposta.rerank ? `reranker, mínimo ${formatar.pct(resposta.limiar)}` : "sem reranker",
      ].filter(Boolean).join(" · ");

  const cabeca = el("div", { class: "resumo" },
    el("h2", { class: "resumo__titulo" },
      `${n} ${n === 1 ? "petição" : "petições"} para `, el("q", {}, resposta.consulta)),
    el("span", { class: "resumo__meta" }, meta),
  );

  const lista = el("ol", { class: "lista" }, resultados.map((r) => el("li", {}, cartao(r, resposta.rerank, termos))));

  mostrar(
    cabeca,
    !resposta.rerank && el("p", { class: "explica-rrf" },
      "Sem o reranker, o número de cada petição é o score RRF: ele só ordena a lista, não mede relevância."),
    lista,
  );
}

function tempoLegivel(ms) {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${formatar.dec(ms / 1000, 1)} s`;
}

function cartao(r, comRerank, termos) {
  const no = ui.tplCartao.content.firstElementChild.cloneNode(true);
  const referencia = `${r.classe} ${r.numero}`;

  no.querySelector(".cartao__pos").textContent = `${r.posicao}.`;
  no.querySelector(".cartao__titulo").textContent = referencia;

  const nota = no.querySelector(".cartao__nota");
  const score = Number(r.score);
  if (comRerank) {
    const pct = Math.max(0, Math.min(1, score));
    nota.append(
      el("span", { class: "nota__valor" }, formatar.pct(pct)),
      el("span", { class: "nota__rotulo" }, "relevância"),
      el("span", { class: "nota__barra", "aria-hidden": "true" }, el("span", { style: `width:${(pct * 100).toFixed(1)}%` })),
    );
  } else {
    nota.classList.add("nota--rrf");
    nota.title = "Só ordena os resultados; não mede relevância.";
    nota.append(
      el("span", { class: "nota__valor" }, formatar.dec(score, 4)),
      el("span", { class: "nota__rotulo" }, "score RRF"),
    );
  }

  const meta = no.querySelector(".cartao__meta");
  const sep = () => el("span", { class: "sep", "aria-hidden": "true" }, "·");
  meta.append(
    el("span", { class: "secao" }, r.secao || "sem seção"), sep(),
    `${r.arquivo_pdf}, p. ${r.pagina}`, sep(),
    `extração ${r.metodo_extracao}`,
  );
  if (r.similaridade !== null && r.similaridade !== undefined) {
    meta.append(sep(), el("span", { title: "Cosseno entre a consulta e o trecho." }, `similaridade ${formatar.dec(Number(r.similaridade), 2)}`));
  }

  const caixaTrecho = no.querySelector(".cartao__trecho");
  const trecho = String(r.trecho ?? "");
  no.querySelector(".trecho").append(grifar(trecho, termos));
  if (trecho.length > LIMITE_TRECHO) {
    const id = `trecho-${r.posicao}`;
    caixaTrecho.id = id;
    caixaTrecho.classList.add("recolhido");
    const botao = no.querySelector(".cartao__expandir");
    botao.hidden = false;
    botao.setAttribute("aria-controls", id);
    botao.setAttribute("aria-expanded", "false");
    botao.addEventListener("click", () => {
      const recolhido = caixaTrecho.classList.toggle("recolhido");
      botao.setAttribute("aria-expanded", String(!recolhido));
      botao.textContent = recolhido ? "Mostrar trecho inteiro" : "Recolher trecho";
    });
  }

  const acoes = no.querySelector(".cartao__acoes");
  const url = api.urlPdfSegura(r.url_pdf);
  if (r.pdf_disponivel && url) {
    acoes.append(el("a", {
      class: "botao botao--primario", href: url, target: "_blank", rel: "noopener",
      "aria-label": `Abrir PDF da ${referencia} na página ${r.pagina}, em nova aba`,
    }, icone("pdf"), `Abrir PDF na p. ${r.pagina}`));
  } else {
    acoes.append(el("span", { class: "sem-pdf" }, "PDF não está neste servidor"));
  }
  const textoRef = `${referencia}, petição inicial, p. ${r.pagina} (${r.arquivo_pdf})`;
  const copiar = el("button", { type: "button", class: "botao botao--fantasma" }, icone("copiar"), "Copiar referência");
  copiar.addEventListener("click", async () => {
    const ok = await copiarTexto(textoRef);
    copiar.replaceChildren(icone(ok ? "ok" : "copiar"), ok ? "Copiada" : "Não deu para copiar");
    setTimeout(() => copiar.replaceChildren(icone("copiar"), "Copiar referência"), 2000);
  });
  acoes.append(copiar);
  return no;
}

async function copiarTexto(texto) {
  try {
    await navigator.clipboard.writeText(texto);
    return true;
  } catch {
    const area = el("textarea", { readonly: true, style: "position:fixed;opacity:0" });
    area.value = texto;
    document.body.append(area);
    area.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { /* sem suporte */ }
    area.remove();
    return ok;
  }
}

let toastTimer;
function toast(texto) {
  let no = document.querySelector(".toast");
  if (!no) { no = el("div", { class: "toast", role: "status" }); document.body.append(no); }
  no.textContent = texto;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => no.remove(), 2600);
}

/* ------------------------------------------------------------------ busca */

function cancelarBusca() {
  if (!estado.busca) return;
  estado.busca.controlador.abort();
}

function encerrarBusca() {
  if (!estado.busca) return;
  clearInterval(estado.busca.timer);
  estado.busca = null;
  ui.painel.setAttribute("aria-busy", "false");
  ui.botaoBuscar.disabled = false;
}

async function buscar(consulta, opcoes = null, { salvarHistorico = true } = {}) {
  consulta = consulta.trim().slice(0, 500);
  if (!consulta) { ui.consulta.focus(); return; }
  if (opcoes) { aplicarOpcoesNoFormulario(opcoes); aoMudarOpcao(); }
  const o = estado.opcoes;

  ui.consulta.value = consulta;
  fecharFolha({ devolverFoco: false });
  cancelarBusca();
  encerrarBusca();

  const urlAtual = new URL(location.href);
  const qAtual = urlAtual.searchParams.get("q") || "";
  if (salvarHistorico && qAtual !== consulta) {
    const url = new URL(location.href);
    url.searchParams.set("q", consulta);
    history.pushState(null, "", url);
  } else if (!salvarHistorico || qAtual === consulta) {
    const url = new URL(location.href);
    url.searchParams.set("q", consulta);
    history.replaceState(null, "", url);
  }

  if (estado.status && !estado.status.indice_pronto) { telaIndiceAusente(); return; }
  if (!navigator.onLine) { mostrarUltimaOuOffline(); return; }

  const controlador = new AbortController();
  const inicio = performance.now();
  const relogio = telaCarregando(o);
  const timer = setInterval(() => { relogio.textContent = `${Math.floor((performance.now() - inicio) / 1000)} s`; }, 250);
  estado.busca = { controlador, timer };
  ui.painel.setAttribute("aria-busy", "true");
  ui.botaoBuscar.disabled = true;

  const vigente = () => estado.busca?.controlador === controlador; // falso se outra busca tomou o lugar

  try {
    const resposta = await api.buscar(
      { consulta, k: o.k, modo: o.modo, classe: o.classe, rerank: o.rerank, limiar: o.limiar },
      { signal: controlador.signal },
    );
    if (!vigente()) return;
    encerrarBusca();
    if (estado.status) estado.status.buscador_carregado = true;
    store.registrarBusca(consulta, o);
    store.salvarUltima(resposta, o);
    telaResultados(resposta);
  } catch (e) {
    if (!vigente()) return;
    encerrarBusca();
    if (e.name === "AbortError") {
      telaErro("Busca cancelada", "Nada foi alterado. Ajuste a consulta ou as opções e busque de novo.");
    } else if (e.tipo === "indice") {
      if (estado.status) estado.status.indice_pronto = false;
      telaIndiceAusente();
    } else if (e.tipo === "rede") {
      navigator.onLine ? telaErro("Servidor fora do ar", "Não deu para falar com o servidor do JurisMatch. Confira se ele está rodando (python -m jurismatch.api) e tente de novo.") : mostrarUltimaOuOffline();
    } else if (e.tipo === "validacao") {
      telaErro("Consulta inválida", e.message, { tentar: false });
    } else {
      telaErro("Algo deu errado na busca", e.message || "Erro inesperado.");
    }
  }
}

function mostrarUltimaOuOffline() {
  atualizarRede();
  const ultima = store.ultima();
  if (ultima?.resposta) {
    const q = ultima.resposta.consulta ?? "";
    ui.consulta.value = q;
    const url = new URL(location.href);
    if (q) url.searchParams.set("q", q);
    else url.searchParams.delete("q");
    history.replaceState(null, "", url);
    telaResultados(ultima.resposta, { offlineDesde: ultima.quando });
  } else {
    telaOfflineSemDados();
  }
}

/* ------------------------------------------------------------------ status e rede */

async function carregarStatus() {
  try {
    estado.status = await api.status({ signal: AbortSignal.timeout?.(8000) });
    const s = estado.status;
    ui.contagem.textContent = s.indice_pronto && s.peticoes != null
      ? ` · ${formatar.int(s.peticoes)} petições, ${formatar.int(s.trechos)} trechos`
      : "";
  } catch {
    estado.status = null; // offline ou servidor fora: a busca decide o que mostrar
  }
}

function atualizarRede() {
  ui.avisoRede.hidden = navigator.onLine;
}

/* ------------------------------------------------------------------ PWA */

function registrarServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  let pediuAtualizacao = false;
  let recarregando = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (pediuAtualizacao && !recarregando) {
      recarregando = true;
      location.reload();
    }
  });
  navigator.serviceWorker.register("/sw.js").then((reg) => {
    const btnAtualizar = $("#btn-atualizar");
    const avisar = (worker) => {
      $("#aviso-versao").hidden = false;
      btnAtualizar.onclick = () => {
        pediuAtualizacao = true;
        btnAtualizar.disabled = true;
        btnAtualizar.textContent = "Atualizando…";
        worker.postMessage({ tipo: "pular-espera" });
      };
    };
    if (reg.waiting && navigator.serviceWorker.controller) avisar(reg.waiting);
    reg.addEventListener("updatefound", () => {
      const novo = reg.installing;
      novo?.addEventListener("statechange", () => {
        if (novo.state === "installed" && navigator.serviceWorker.controller) avisar(novo);
      });
    });
  }).catch(() => { /* sem SW (http em IP da rede, por exemplo): o app funciona online */ });
}

function prepararInstalacao() {
  const botao = $("#btn-instalar");
  let pedido = null;
  window.addEventListener("beforeinstallprompt", (ev) => {
    ev.preventDefault();
    pedido = ev;
    botao.hidden = false;
  });
  botao.addEventListener("click", async () => {
    if (!pedido) return;
    botao.hidden = true;
    pedido.prompt();
    await pedido.userChoice.catch(() => null);
    pedido = null;
  });
  window.addEventListener("appinstalled", () => { botao.hidden = true; toast("JurisMatch instalado."); });

  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const instalado = window.navigator.standalone || window.matchMedia("(display-mode: standalone)").matches;
  if (ios && !instalado && !store.dicaIosDispensada()) {
    $("#dica-ios").hidden = false;
    $("#btn-fechar-ios").addEventListener("click", () => { store.dispensarDicaIos(); $("#dica-ios").hidden = true; });
  }
}

/* ------------------------------------------------------------------ início */

function ligarEventos() {
  ui.form.addEventListener("submit", (ev) => { ev.preventDefault(); buscar(ui.consulta.value); });

  const aoLimparCampo = () => {
    if (!ui.consulta.value && !estado.busca && (!estado.status || estado.status.indice_pronto)) {
      const url = new URL(location.href);
      url.searchParams.delete("q");
      history.replaceState(null, "", url);
      telaInicio();
    }
  };
  ui.consulta.addEventListener("input", aoLimparCampo);
  ui.consulta.addEventListener("search", aoLimparCampo);

  ui.opcoes.addEventListener("input", aoMudarOpcao);
  ui.opcoes.addEventListener("change", aoMudarOpcao);

  ui.botaoOpcoes.addEventListener("click", abrirFolha);
  $("#btn-fechar-opcoes").addEventListener("click", () => fecharFolha());
  $("#btn-aplicar").addEventListener("click", () => fecharFolha());
  ui.fundo.addEventListener("click", () => fecharFolha());
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") fecharFolha(); });
  ehDesktop.addEventListener("change", () => fecharFolha({ devolverFoco: false }));

  window.addEventListener("online", () => {
    atualizarRede();
    carregarStatus();
    if (!document.querySelector(".lista") && !document.querySelector(".carregando")) {
      const q = ui.consulta.value.trim();
      if (q) buscar(q, null, { salvarHistorico: false });
      else telaInicio();
    }
  });
  window.addEventListener("offline", atualizarRede);

  window.addEventListener("popstate", () => {
    const q = new URLSearchParams(location.search).get("q")?.trim() || "";
    ui.consulta.value = q;
    if (q) {
      buscar(q, null, { salvarHistorico: false });
    } else {
      cancelarBusca();
      encerrarBusca();
      telaInicio();
    }
  });
}

async function iniciar() {
  aplicarOpcoesNoFormulario(estado.opcoes);
  ligarEventos();
  registrarServiceWorker();
  prepararInstalacao();
  atualizarRede();

  const q = new URLSearchParams(location.search).get("q")?.trim();
  if (!navigator.onLine) {
    if (q) ui.consulta.value = q;
    mostrarUltimaOuOffline();
    return;
  }

  telaInicio();
  await carregarStatus();
  if (estado.status && !estado.status.indice_pronto) {
    if (q) ui.consulta.value = q;
    telaIndiceAusente();
  } else if (q) {
    buscar(q);
  } else if (!estado.status) {
    // servidor não respondeu: se houver última busca, ela ainda é útil
    const ultima = store.ultima();
    if (ultima?.resposta) telaResultados(ultima.resposta, { offlineDesde: ultima.quando });
  }
}

iniciar();
