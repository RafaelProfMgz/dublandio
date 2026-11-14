// dublandio: interface local. Sem build: DOM puro, um estado e uma função de render por tela.

const CORES = ["#2F7ED8", "#E07A1F", "#2BA84A", "#9B4DCA", "#D6457A", "#1BA3A3",
               "#B8A21A", "#6C63D9", "#C2563A", "#4E9A8B", "#A35C9E", "#7A8A2E"];
const NARRADOR = "Narrador";
const NOVO = "+novo";  // rota da tela "Adicionar livro"; o "+" nunca aparece num slug
const ROTULO_ETAPA = { preparar: "Preparando roteiros", separar: "Separando falas", sintetizar: "Sintetizando", video: "Gerando vídeo" };

const estado = {
  livros: [],
  slug: null,
  livro: null,
  aba: "capitulos",   // capitulos | vozes | config
  cap: null,          // capítulo aberto no editor
  selecionados: new Set(),
  sujo: false,        // editor com mudanças não salvas
  hash: location.hash,
  tarefa: null,       // {etapa, livro, total, feitas, fonte}
  tocando: null,
  catalogo: {},       // provedor -> {vozes, buscado_em}
  chaves: null,       // situação da chave de cada provedor (GET /api/chaves)
  videos: null,
  pastaVersao: 0,
  filtro: { busca: "", idioma: null, genero: "", multilingue: true },
};
const player = new Audio();
const $ = (id) => document.getElementById(id);
const reprodutor = new ReprodutorAudio(player, $("reprodutor"), {
  aoMudar: (item, tocando) => {
    const chave = tocando ? item.chave : null;
    if (estado.tocando !== chave) { estado.tocando = chave; marcarTocando(); }
  },
  aoFalhar: (mensagem) => avisar(mensagem, true),
});

// ---------- utilitários ----------

function h(tag, atributos = {}, ...filhos) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(atributos)) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "style" && typeof v === "object") for (const [p, x] of Object.entries(v)) el.style.setProperty(p, x);
    else if (k === "class") el.className = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const f of filhos.flat()) if (f != null && f !== false) el.append(f instanceof Node ? f : String(f));
  return el;
}

const SVG = "http://www.w3.org/2000/svg";
function icone(nome) {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", "icone");
  svg.setAttribute("aria-hidden", "true");
  const uso = document.createElementNS(SVG, "use");
  uso.setAttribute("href", `#i-${nome}`);
  svg.append(uso);
  return svg;
}

async function api(caminho, opcoes = {}) {
  const resp = await fetch(caminho, {
    ...opcoes,
    headers: opcoes.body ? { "Content-Type": "application/json" } : undefined,
  });
  const dados = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(Array.isArray(dados.detail) ? dados.detail.map((x) => x.msg).join("; ") : dados.detail || `erro ${resp.status}`);
  return dados;
}

let temporizadorAviso;
function avisar(texto, erro = false) {
  const el = $("aviso");
  el.textContent = texto;
  el.className = erro ? "aviso erro" : "aviso";
  el.hidden = false;
  clearTimeout(temporizadorAviso);
  temporizadorAviso = setTimeout(() => (el.hidden = true), erro ? 6000 : 2800);
}

function confirmar(titulo, conteudo, rotuloOk, { gravar = false } = {}) {
  const dialogo = $("dialogo");
  $("dialogo-titulo").textContent = titulo;
  $("dialogo-texto").replaceChildren(...[conteudo].flat().filter(Boolean));
  const ok = $("dialogo-ok");
  ok.textContent = rotuloOk;
  ok.className = gravar ? "botao gravar" : "botao primario";
  dialogo.returnValue = "";
  dialogo.showModal();
  ok.focus();
  return new Promise((resolve) => dialogo.addEventListener("close", () => resolve(dialogo.returnValue === "ok"), { once: true }));
}

const nomeCap = (cap) => `Capítulo ${Number(cap.slice(4))}`;
const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;

function corDe(personagem) {
  if (personagem === NARRADOR) return "var(--narrador)";
  const ordem = (estado.livro?.vozes || []).map((v) => v.personagem).filter((p) => p !== NARRADOR);
  const i = ordem.indexOf(personagem);
  return CORES[(i < 0 ? ordem.length : i) % CORES.length];
}

// ---------- navegação ----------

function lerHash() {
  const [slug, resto] = location.hash.replace(/^#\/?/, "").split("/");
  return { slug: slug || null, resto: resto || "" };
}

function ir(slug, resto = "") {
  location.hash = `#/${slug}${resto ? "/" + resto : ""}`;
}

async function aoMudarHash() {
  if (estado.sujo && location.hash !== estado.hash) {
    const sair = await confirmar("Descartar mudanças?", h("p", {}, "O texto editado ainda não foi salvo."), "Descartar");
    if (!sair) {
      history.replaceState(null, "", estado.hash);
      return;
    }
    estado.sujo = false;
  }
  estado.hash = location.hash;
  const { slug, resto } = lerHash();
  $("adicionar-livro").setAttribute("aria-current", slug === NOVO ? "page" : "false");
  if (slug === "+video") {
    estado.slug = null;
    estado.livro = null;
    renderLateral();
    telaNovoVideo();
    return;
  }
  if (slug === NOVO) {
    estado.slug = null;
    estado.livro = null;
    renderLateral();
    telaNovoLivro();
    return;
  }
  if (!slug) {
    if (estado.livros.length) ir(estado.livros[0].slug);
    else renderVazioGeral();
    return;
  }
  estado.aba = ["vozes", "catalogo", "config", "videos"].includes(resto) ? resto : "capitulos";
  estado.cap = /^cap_\d{3}$/.test(resto) ? resto : null;
  if (slug !== estado.slug) {
    estado.slug = slug;
    estado.selecionados.clear();
    estado.livro = null;
    estado.videos = null;
    renderLateral();
    $("principal").replaceChildren(h("div", { class: "vazio" }, "Abrindo o livro…"));
    await recarregarLivro();
  } else {
    render();
  }
}

function aplicarTema(tema) {
  if (tema === "light" || tema === "dark") document.documentElement.dataset.theme = tema;
  else delete document.documentElement.dataset.theme;
  for (const b of document.querySelectorAll(".tema button")) b.setAttribute("aria-checked", String(b.dataset.tema === (tema || "auto")));
}
function temaSalvo() { try { return localStorage.getItem("dublandio-tema") || "auto"; } catch { return "auto"; } }
for (const b of document.querySelectorAll(".tema button")) {
  b.addEventListener("click", () => {
    try { localStorage.setItem("dublandio-tema", b.dataset.tema); } catch { /* sem armazenamento: vale só nesta aba */ }
    aplicarTema(b.dataset.tema);
  });
}
aplicarTema(temaSalvo());

window.addEventListener("hashchange", aoMudarHash);
window.addEventListener("beforeunload", (e) => { if (estado.sujo) e.preventDefault(); });

// ---------- dados ----------

async function carregarLivros() {
  estado.livros = await api("/api/livros");
  renderLateral();
}

async function recarregarLivro() {
  const slug = estado.slug;
  try {
    const dados = await api(`/api/livros/${slug}`);
    if (estado.slug !== slug || lerHash().slug !== slug) return;
    estado.livro = dados;
  } catch (e) {
    if (estado.slug !== slug) return;
    estado.livro = null;
    $("principal").replaceChildren(h("div", { class: "vazio" }, h("h2", {}, "Não deu para abrir este livro"), e.message));
    return;
  }
  render();
}

async function carregarChaves(atualizar = false) {
  try {
    estado.chaves = await api(`/api/chaves${atualizar ? "?atualizar=true" : ""}`);
  } catch (e) {
    estado.chaves = null;
    if (atualizar) avisar(e.message, true);
  }
  renderChaves();
  render();
}

const chaveDe = (provedor) => estado.chaves?.find((c) => c.provedor === provedor);
const dinheiro = (v) => v.toLocaleString("pt-BR", { style: "currency", currency: "USD" });

// O que as chaves do livro (principal e reserva) permitem; null quando está tudo certo.
function chavesDoLivro(l) {
  const principal = chaveDe(l.provedor);
  if (!principal) return null;
  const reserva = l.reserva ? chaveDe(l.reserva) : null;
  const problemas = [principal, reserva].filter((c) => c && c.situacao !== "ok");
  if (!problemas.length) return null;
  const bloqueado = principal.bloqueia && (!reserva || reserva.bloqueia);
  let titulo;
  if (bloqueado) titulo = "Não dá para sintetizar agora";
  else if (principal.bloqueia) titulo = `${principal.rotulo} fora: a síntese vai usar a reserva (${reserva.rotulo})`;
  else if (reserva?.bloqueia) titulo = `Reserva (${reserva.rotulo}) indisponível: se o principal (${principal.rotulo}) parar, a síntese para junto`;
  else titulo = "Não deu para conferir as chaves agora";
  return { bloqueado, titulo, problemas };
}

function alertaChaves(l) {
  const s = chavesDoLivro(l);
  if (!s) return null;
  return h("div", { class: `alerta-chave ${s.bloqueado ? "erro" : "atencao"}`, role: s.bloqueado ? "alert" : "status" },
    h("strong", { class: "alerta-titulo" }, s.titulo),
    s.problemas.map((c) => h("p", {}, c.mensagem)),
    h("div", { class: "alerta-acoes" },
      s.problemas.filter((c) => ["ausente", "invalida"].includes(c.situacao)).map((c) =>
        h("button", { class: "botao primario", type: "button", onclick: () => pedirChave(c) }, rotuloChave(c))),
      s.problemas.filter((c) => c.link_credito).map((c) =>
        h("a", { class: "botao", href: c.link_credito, target: "_blank", rel: "noopener" }, `Adicionar créditos (${c.rotulo})`)),
      h("button", { class: "botao sutil", type: "button", onclick: () => carregarChaves(true) }, "Conferir de novo"),
    ),
  );
}

const rotuloChave = (c) => `${c.final ? "Trocar" : "Colocar"} chave ${c.rotulo}`;

// Pede a chave num diálogo; o servidor confere com o provedor antes de gravar no .env.
async function pedirChave(c) {
  let erro = null;
  for (;;) {
    const campo = h("input", {
      type: "password", class: "campo-chave", autocomplete: "off", spellcheck: "false",
      placeholder: "cole a chave aqui", "aria-label": `Chave ${c.rotulo}`,
    });
    // Enter salva (o botão padrão do formulário seria o Cancelar).
    campo.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); $("dialogo").close("ok"); } });
    setTimeout(() => campo.focus());
    const ok = await confirmar(rotuloChave(c), [
      h("p", {}, `Cole a chave da sua conta ${c.rotulo}. Ela é conferida antes de salvar e fica só neste computador, no arquivo .env.`),
      c.final ? h("p", {}, `A chave atual termina em …${c.final}.`) : null,
      campo,
      erro ? h("p", { class: "erro-campo", role: "alert" }, erro) : null,
      h("p", {}, h("a", { href: c.link_chave, target: "_blank", rel: "noopener" }, "Onde pego a chave?")),
    ], "Conferir e salvar");
    if (!ok) return;
    avisar("Conferindo a chave…");
    try {
      await api(`/api/chaves/${c.provedor}`, { method: "PUT", body: JSON.stringify({ chave: campo.value }) });
    } catch (e) {
      $("aviso").hidden = true;  // o erro aparece dentro do diálogo
      erro = e.message;
      continue;
    }
    avisar(`Chave ${c.rotulo} salva e funcionando`);
    if (c.provedor === "huggingface") estado.videos = null;
    await carregarChaves();
    return;
  }
}

function renderChaves() {
  const el = $("chaves");
  if (!estado.chaves) {
    el.replaceChildren(h("div", { class: "chaves-topo" }, h("span", {}, "Conferindo chaves…")));
    return;
  }
  el.replaceChildren(
    h("div", { class: "chaves-topo" },
      h("h2", { class: "lateral-titulo" }, icone("chave"), "Chaves"),
      h("button", { class: "botao-icone", type: "button", title: "Conferir de novo", "aria-label": "Conferir as chaves de novo",
                    onclick: () => carregarChaves(true) }, "↻"),
    ),
    h("ul", {}, estado.chaves.map((c) => h("li", {},
      h("button", {
        class: "chave", type: "button", "data-situacao": c.situacao,
        title: `${c.mensagem}\nClique para ${c.final ? "trocar" : "colocar"} a chave.`, onclick: () => pedirChave(c),
      },
        h("span", { class: "chave-luz", "aria-hidden": "true" }),
        h("span", { class: "chave-nome" }, c.rotulo),
        h("span", { class: "chave-estado" }, c.curto, c.saldo != null && c.situacao === "ok" ? ` · ${dinheiro(c.saldo)}` : ""),
      ),
    ))),
  );
}

// ---------- barra lateral ----------

// Cor estável por livro (a mesma paleta dos personagens).
function corDoLivro(slug) {
  let n = 0;
  for (const c of slug) n = (n * 31 + c.charCodeAt(0)) >>> 0;
  return CORES[n % CORES.length];
}

function renderLateral() {
  $("livros").replaceChildren(...estado.livros.map((l) => {
    const pct = l.capitulos ? Math.round((100 * l.com_audio) / l.capitulos) : 0;
    return h("li", {},
      h("button", {
        class: "livro-link", type: "button", "aria-current": l.slug === estado.slug ? "page" : null,
        onclick: () => ir(l.slug), style: { "--cor": corDoLivro(l.slug) },
      },
        h("span", { class: "livro-inicial", "aria-hidden": "true" }, (l.titulo.match(/[\p{L}\p{N}]/u) || ["?"])[0].toUpperCase()),
        h("span", { class: "livro-titulo" }, l.titulo),
        h("span", { class: "livro-meta" }, l.erro ? "livro.yaml com erro"
          : `${l.com_audio} de ${plural(l.capitulos, "capítulo", "capítulos")} com áudio`),
        h("span", { class: "livro-progresso", "aria-hidden": "true" }, h("span", { style: { width: `${pct}%` } })),
      ));
  }));
}

function renderVazioGeral() {
  $("principal").replaceChildren(h("div", { class: "vazio" },
    h("h2", {}, "Nenhum livro ainda"),
    h("p", {}, "Use Adicionar livro para escolher a pasta com os capítulos."),
  ));
}

// ---------- tela do livro ----------

function render() {
  if (lerHash().slug === NOVO) return;
  const l = estado.livro;
  if (!l) return;
  if (estado.sujo) return;  // reconstruir a tela recarregaria o editor e perderia o texto
  const principal = $("principal");
  if (estado.cap) {
    principal.replaceChildren(cabecalho(l), alertaChaves(l) || "", telaCapitulo(l));
    return;
  }
  const abas = h("div", { class: "abas", role: "tablist" },
    aba("capitulos", "Capítulos", l.lista.length),
    aba("vozes", "Vozes", l.vozes.length),
    aba("videos", "Vídeos"),
    aba("catalogo", "Catálogo"),
    aba("config", "Configuração"),
  );
  const corpo = { capitulos: telaCapitulos, vozes: telaVozes, catalogo: telaCatalogo, config: telaConfig, videos: telaVideos }[estado.aba](l);
  principal.replaceChildren(h("div", { class: "topo-livro" }, cabecalho(l), abas), alertaChaves(l) || "", corpo);
}

function aba(id, rotulo, contagem) {
  return h("button", {
    class: "aba", role: "tab", type: "button", "aria-selected": String(estado.aba === id),
    onclick: () => ir(estado.slug, id === "capitulos" ? "" : id),
  }, icone(id), rotulo, contagem != null ? h("span", { class: "aba-contagem" }, contagem) : null);
}

function cabecalho(l) {
  const ocupado = !!estado.tarefa;
  const selecao = [...estado.selecionados];
  const semChave = chavesDoLivro(l)?.bloqueado;
  return h("header", { class: "cabecalho" },
    h("div", {},
      h("h1", {}, l.titulo),
      h("div", { class: "cabecalho-sub" },
        h("span", { class: "provedor" }, l.provedor), "  ",
        l.reserva ? [h("span", { class: "provedor reserva", title: "Usado quando a cota do principal acaba" }, `reserva: ${l.reserva}`), "  "] : null,
        `${l.com_audio} de ${plural(l.capitulos, "capítulo", "capítulos")} com áudio`),
    ),
    estado.cap ? null : h("div", { class: "acoes" },
      l.tem_origem ? h("button", {
        class: "botao", type: "button", disabled: ocupado,
        title: "Gera roteiros a partir do manuscrito. Roteiros que já existem não são tocados.",
        onclick: () => rodar("preparar"),
      }, "Preparar roteiros") : null,
      h("button", {
        class: "botao", type: "button", disabled: ocupado,
        title: "Lê os roteiros e resolve a voz de cada fala",
        onclick: () => rodar("separar"),
      }, "Separar falas"),
      h("button", {
        class: "botao gravar", type: "button", disabled: ocupado || semChave || !l.lista.some((c) => c.tem_manifesto),
        title: semChave ? "Resolva a chave do provedor (aviso abaixo) para sintetizar" : null,
        onclick: () => rodar("sintetizar", selecao),
      }, selecao.length ? `Sintetizar ${plural(selecao.length, "capítulo", "capítulos")}` : "Sintetizar todos"),
    ),
  );
}

// ---------- capítulos ----------

function faixa(c) {
  if (!c.falas.length) {
    return h("div", { class: "faixa-vazia" }, c.tem_roteiro ? "Rode Separar falas para ver as falas" : "Sem roteiro");
  }
  return h("div", {
    class: c.falas.length > 160 ? "faixa densa" : "faixa", "data-cap": c.cap, role: "img",
    "aria-label": `${c.falas.length} falas, ${c.pendentes} por sintetizar`,
  }, c.falas.map((f) => h("span", {
    class: f.em_cache ? "faixa-fala feita" : "faixa-fala", "data-ordem": f.ordem,
    title: `${f.ordem}. ${f.personagem}`, style: { "--cor": corDe(f.personagem) },
  })));
}

function descricaoEstado(c) {
  const partes = [];
  if (!c.tem_roteiro && !c.tem_manifesto) partes.push("Sem roteiro");
  else if (!c.tem_manifesto) partes.push(h("span", { class: "atencao" }, "Falta separar as falas"));
  else {
    if (c.tem_audio) {
      partes.push(h("span", { class: "ok" }, "Áudio pronto"));
      // Áudio feito sem o cache atual (ex.: scripts antigos): refazer gera tudo de novo.
      partes.push(c.pendentes ? `refazer gera ${plural(c.pendentes, "fala", "falas")}` : plural(c.falas.length, "fala", "falas"));
    } else {
      partes.push(plural(c.falas.length, "fala", "falas"));
      if (c.pendentes) partes.push(h("span", { class: "pendente" }, `${c.pendentes} por sintetizar`));
      else if (c.falas.length) partes.push(h("span", { class: "atencao" }, "falta montar o áudio"));
    }
  }
  if (c.manifesto_desatualizado) partes.push(h("span", { class: "atencao" }, "roteiro mudou depois do separar"));
  return h("div", { class: "capitulo-estado" }, ...partes.flatMap((p, i) => (i ? [h("br"), p] : [p])));
}

// Um player só, para capítulos e amostras de voz; `chave` identifica o que está tocando.
function botaoTocar(chave, url, rotulo, opcoes = {}) {
  const tocando = estado.tocando === chave;
  const botao = h("button", {
    class: "tocar", type: "button", "data-tocar": chave, "aria-pressed": String(tocando),
    "aria-label": `${tocando ? "Pausar" : "Ouvir"} ${rotulo}`,
    onclick: () => alternarAudio(chave, url, rotulo, opcoes),
  });
  botao.append(iconeTocar(tocando));
  return botao;
}

function marcarTocando() {
  document.querySelectorAll("[data-tocar]").forEach((b) => {
    const tocando = b.dataset.tocar === estado.tocando;
    b.setAttribute("aria-pressed", String(tocando));
    b.setAttribute("aria-label", b.getAttribute("aria-label").replace(/^(Pausar|Ouvir)/, tocando ? "Pausar" : "Ouvir"));
    b.replaceChildren(iconeTocar(tocando));
  });
}

function botaoTocarCapitulo(c) {
  if (!c.tem_audio) return null;
  const slug = estado.slug;
  const livro = estado.livro;
  const fila = livro.lista.filter((cap) => cap.tem_audio).map((cap) => ({
    chave: `cap:${slug}:${cap.cap}`, url: `/api/livros/${slug}/audio/${cap.cap}?v=${cap.audio_versao}`,
    titulo: nomeCap(cap.cap), subtitulo: livro.titulo,
  }));
  const item = fila.find((f) => f.chave === `cap:${slug}:${c.cap}`);
  return botaoTocar(item.chave, item.url, item.titulo, { item, fila });
}

function iconeTocar(tocando) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 12 12");
  svg.innerHTML = tocando ? '<rect x="2" y="1" width="3" height="10"/><rect x="7" y="1" width="3" height="10"/>'
                          : '<path d="M3 1.2v9.6L11 6z"/>';
  return svg;
}

function faixaVoz(v) {
  return { chave: `voz:${v.id}`, url: v.amostra, titulo: v.nome, subtitulo: `Amostra de voz · ${rotuloIdioma(v.idioma)}` };
}

function alternarAudio(chave, url, rotulo, opcoes = {}) {
  const item = opcoes.item || { chave, url, titulo: rotulo, subtitulo: "Amostra de voz" };
  const fila = typeof opcoes.fila === "function" ? opcoes.fila() : opcoes.fila || [item];
  reprodutor.alternar(item, fila);
}

function telaCapitulos(l) {
  if (!l.lista.length) {
    return h("div", { class: "vazio" },
      h("h2", {}, "Nenhum capítulo ainda"),
      l.tem_origem ? "Use Preparar roteiros para gerar os roteiros a partir do manuscrito."
                   : "Este livro não tem origem no livro.yaml: escreva os roteiros em roteiro/cap_NNN.txt.");
  }
  const todos = l.lista.every((c) => estado.selecionados.has(c.cap));
  const pendentes = l.lista.reduce((s, c) => s + c.pendentes, 0);
  return h("div", {},
    h("div", { class: "barra-selecao" },
      h("label", {},
        h("input", {
          type: "checkbox", checked: todos,
          onchange: (e) => { l.lista.forEach((c) => e.target.checked ? estado.selecionados.add(c.cap) : estado.selecionados.delete(c.cap)); render(); },
        }),
        estado.selecionados.size ? `${estado.selecionados.size} selecionado(s)` : "Selecionar todos"),
      h("span", {}, pendentes ? `${plural(pendentes, "fala", "falas")} por sintetizar no livro` : "Todas as falas já foram sintetizadas"),
    ),
    h("ul", { class: "capitulos" }, l.lista.map((c) => h("li", { class: "capitulo" },
      h("input", {
        type: "checkbox", checked: estado.selecionados.has(c.cap), "aria-label": `Selecionar ${nomeCap(c.cap)}`,
        onchange: (e) => { e.target.checked ? estado.selecionados.add(c.cap) : estado.selecionados.delete(c.cap); render(); },
      }),
      h("button", { class: "capitulo-nome", type: "button", onclick: () => ir(estado.slug, c.cap), title: "Abrir o roteiro" }, nomeCap(c.cap)),
      faixa(c),
      descricaoEstado(c),
      h("div", { class: "capitulo-acoes" }, botaoTocarCapitulo(c),
        c.tem_audio ? h("button", { class: "botao sutil", type: "button", onclick: () => ir(estado.slug, "videos") }, "Vídeo") : null),
    ))),
  );
}

// ---------- capítulo aberto ----------

function telaCapitulo(l) {
  const c = l.lista.find((x) => x.cap === estado.cap);
  if (!c) return h("div", { class: "vazio" }, h("h2", {}, `${estado.cap} não existe neste livro`));

  const salvar = h("button", { class: "botao primario", type: "button", disabled: true, onclick: () => salvarRoteiro() }, "Salvar roteiro");
  const area = h("textarea", {
    class: "roteiro", spellcheck: "true", "aria-label": `Roteiro do ${nomeCap(c.cap)}`, disabled: true,
    oninput: () => { estado.sujo = true; salvar.disabled = false; },
    onkeydown: (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); if (estado.sujo) salvarRoteiro(); }
    },
  }, "Carregando…");

  async function salvarRoteiro() {
    salvar.disabled = true;
    try {
      const r = await api(`/api/livros/${estado.slug}/roteiro/${c.cap}`, { method: "PUT", body: JSON.stringify({ texto: area.value }) });
      estado.sujo = false;
      avisar(r.aviso || "Roteiro salvo e falas separadas", !!r.aviso);
      await recarregarLivro();
    } catch (e) {
      salvar.disabled = false;
      avisar(e.message, true);
    }
  }

  if (c.tem_roteiro) {
    api(`/api/livros/${estado.slug}/roteiro/${c.cap}`).then((r) => {
      area.value = r.texto;
      area.disabled = false;
    }).catch((e) => { area.value = e.message; });
  } else {
    area.value = "Este capítulo não tem roteiro.";
  }

  const elenco = {};
  c.falas.forEach((f) => (elenco[f.personagem] = (elenco[f.personagem] || 0) + 1));

  return h("div", {},
    h("div", { class: "trilha" },
      h("button", { type: "button", onclick: () => ir(estado.slug) }, "Capítulos"), " / ", nomeCap(c.cap)),
    h("div", { class: "editor-grade" },
      h("div", {},
        h("div", { class: "folha" },
          h("div", { class: "folha-topo" }, h("span", {}, `roteiro/${c.cap}.txt`), salvar),
          area),
        h("p", { class: "dica" },
          "Uma fala por bloco, separada por linha vazia, no formato ", h("strong", {}, "Nome: fala"),
          ". Sem nome, o bloco é do Narrador. Salvar separa as falas de novo. ", h("kbd", {}, "Ctrl"), " + ", h("kbd", {}, "S"), " salva."),
      ),
      h("aside", { class: "painel" },
        h("section", {},
          h("h3", {}, "Falas"),
          faixa(c),
          h("p", { class: "dica" }, c.falas.length ? `${plural(c.falas.length, "fala", "falas")}, ${c.pendentes} por sintetizar` : ""),
          h("button", {
            class: "botao gravar", type: "button", disabled: !!estado.tarefa || !c.tem_manifesto,
            onclick: () => rodar("sintetizar", [c.cap]),
          }, c.pendentes ? "Sintetizar capítulo" : "Montar áudio"),
        ),
        c.tem_audio ? h("section", {},
          h("h3", {}, "Ouvir"),
          botaoTocarCapitulo(c),
          h("p", { class: "dica" }, "Controle a reprodução na barra inferior."),
        ) : null,
        Object.keys(elenco).length ? h("section", {},
          h("h3", {}, "Vozes do capítulo"),
          h("ul", { class: "elenco" }, Object.entries(elenco).sort((a, b) => b[1] - a[1]).map(([p, n]) => h("li", {},
            h("div", { class: "elenco-personagem" }, h("span", { class: "amostra", style: { "--cor": corDe(p) } }), p, h("span", { class: "numero" }, n)),
            botaoEscolherVoz(l, p)))),
          h("p", { class: "dica" }, "A voz do personagem vale para todos os capítulos deste livro."),
        ) : null,
      ),
    ),
  );
}

// ---------- vozes ----------

function telaVozes(l) {
  if (!l.vozes.length) {
    return h("div", { class: "vazio" }, h("h2", {}, "Ninguém fala ainda"), "Rode Separar falas para contar os personagens.");
  }
  const semVoz = l.vozes.filter((v) => !v.voz_propria).length;
  return h("div", {},
    h("table", { class: "tabela" },
      h("thead", {}, h("tr", {},
        h("th", {}, "Personagem"), h("th", { class: "numero" }, "Falas"), h("th", {}, `Voz no ${l.provedor}`))),
      h("tbody", {}, l.vozes.map((v) => h("tr", {},
        h("td", {}, h("span", { class: "nome-cor" }, h("span", { class: "amostra", style: { "--cor": corDe(v.personagem) } }), v.personagem)),
        h("td", { class: "numero" }, v.falas),
        h("td", {},
          botaoEscolherVoz(l, v.personagem),
          v.voz_propria ? null : h("div", { class: "herdada" }, "Sem voz própria: usa a do Narrador")),
      ))),
    ),
    h("p", { class: "dica" },
      semVoz ? `${plural(semVoz, "personagem usa", "personagens usam")} a voz do Narrador. ` : "",
      "Escolha uma voz para salvar e atualizar as falas do livro. Apelidos: ",
      h("button", { class: "botao sutil", type: "button", onclick: () => ir(estado.slug, "config") }, "editar configuração"),
    ),
  );
}

// ---------- catálogo de vozes ----------

const NOMES_IDIOMA = {
  Portuguese: "Português", English: "Inglês", Spanish: "Espanhol", French: "Francês", German: "Alemão",
  Italian: "Italiano", Japanese: "Japonês", Multilingual: "Multilíngue", "": "Sem idioma",
};
const NOMES_GENERO = { female: "Feminina", male: "Masculina" };
const LOTE = 120;
const rotuloIdioma = (i) => NOMES_IDIOMA[i] ?? i;

const buscasCatalogo = {};
function obterCatalogo(provedor) {
  if (estado.catalogo[provedor]) return Promise.resolve(estado.catalogo[provedor]);
  return buscasCatalogo[provedor] ||= carregarCatalogo(provedor).finally(() => delete buscasCatalogo[provedor]);
}

function sotaqueDaVoz(v) {
  if (v.sotaque) return v.sotaque;
  // Só reconhece termos explícitos do nome; idioma não determina sotaque.
  const termos = { British: "Britânico", Brazilian: "Brasileiro", American: "Americano",
    Scottish: "Escocês", Irish: "Irlandês", Australian: "Australiano", Yorkshire: "Yorkshire", Lancashire: "Lancashire" };
  return Object.entries(termos).find(([termo]) => new RegExp(`\\b${termo}\\b`, "i").test(v.nome))?.[1] || "";
}

function botaoEscolherVoz(l, personagem) {
  const propria = l.mapa_vozes[personagem];
  const id = propria || l.mapa_vozes[NARRADOR];
  const botao = h("button", { class: "seletor-voz", type: "button", "aria-haspopup": "dialog",
    "aria-label": `Escolher voz de ${personagem}`, "data-personagem-voz": personagem,
    disabled: !!estado.tarefa, onclick: () => abrirSeletorVoz(l, personagem, botao) });
  const rotular = (dados) => {
    const voz = dados?.vozes.find((v) => v.id === id);
    botao.replaceChildren(h("span", {}, voz?.nome || id || "Selecionar voz"), h("span", { "aria-hidden": "true" }, "⌄"));
    if (!propria && personagem !== NARRADOR) botao.append(h("small", {}, "Voz do Narrador"));
  };
  rotular(estado.catalogo[l.provedor]);
  if (!estado.catalogo[l.provedor]) obterCatalogo(l.provedor).then(rotular).catch(() => {});
  return botao;
}

function abrirSeletorVoz(l, personagem, origem) {
  const slug = estado.slug;
  const atual = l.mapa_vozes[personagem] || l.mapa_vozes[NARRADOR];
  const modal = h("dialog", { class: "dialogo seletor-vozes", "aria-labelledby": "seletor-voz-titulo" });
  const fechar = h("button", { class: "botao", type: "button", onclick: () => modal.close() }, "Fechar");
  const corpo = h("div", {}, h("p", { role: "status" }, "Carregando vozes…"));
  let salvando = false;
  modal.append(h("div", { class: "seletor-cabecalho" }, h("h2", { id: "seletor-voz-titulo" }, `Voz de ${personagem}`), fechar),
    h("p", { class: "dica" }, "Escolha uma voz para o personagem em todos os capítulos do livro. Ouvir amostras não gasta créditos."), corpo);
  modal.addEventListener("cancel", (e) => { if (salvando) e.preventDefault(); });
  modal.addEventListener("close", () => {
    modal.remove();
    if (origem.isConnected) origem.focus();
    else document.querySelectorAll("[data-personagem-voz]").forEach((b) => { if (b.dataset.personagemVoz === personagem) b.focus(); });
  }, { once: true });
  document.body.append(modal);
  modal.showModal();
  reprodutor.acoplarModal(modal);

  async function montar(atualizar = false) {
    try {
      const dados = atualizar ? await carregarCatalogo(l.provedor, true) : await obterCatalogo(l.provedor);
      if (!modal.open) return;
      const busca = h("input", { type: "search", class: "campo busca", placeholder: "Buscar nome, descrição ou idioma", "aria-label": "Buscar voz" });
      const genero = h("select", { class: "campo", "aria-label": "Filtrar gênero" },
        h("option", { value: "" }, "Todos os gêneros"),
        Object.entries(NOMES_GENERO).map(([id, nome]) => h("option", { value: id }, nome)),
        h("option", { value: "?" }, "Gênero não informado"));
      const sotaques = [...new Set(dados.vozes.map(sotaqueDaVoz).filter(Boolean))].sort((a, b) => a.localeCompare(b, "pt-BR"));
      const sotaque = h("select", { class: "campo", "aria-label": "Filtrar sotaque" },
        h("option", { value: "" }, "Todos os sotaques"), sotaques.map((s) => h("option", { value: s }, s)),
        h("option", { value: "?" }, "Sotaque não informado"));
      const resumo = h("p", { class: "dica", role: "status", "aria-live": "polite" });
      const erro = h("p", { class: "erro", role: "alert", hidden: true });
      const lista = h("ul", { class: "escolhas-vozes", "aria-label": "Vozes disponíveis" });
      let limite = LOTE;
      const normalizar = (s) => String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
      async function selecionar(v) {
        if (salvando) return;
        salvando = true;
        fechar.disabled = true;
        erro.hidden = true;
        lista.querySelectorAll("button").forEach((b) => b.disabled = true);
        try {
          const r = await api(`/api/livros/${slug}/voz`, { method: "PUT", body: JSON.stringify({ personagem, voz: v.id, provedor: l.provedor }) });
          const novo = await api(`/api/livros/${slug}`);
          if (estado.slug === slug) {
            estado.livro = novo;
            if (estado.sujo) {
              document.querySelectorAll("[data-personagem-voz]").forEach((b) => b.replaceWith(botaoEscolherVoz(novo, b.dataset.personagemVoz)));
            } else render();
          }
          modal.close();
          avisar(r.aviso || `Voz de ${personagem} atualizada`, !!r.aviso);
        } catch (e) { erro.textContent = e.message; erro.hidden = false; }
        finally { salvando = false; fechar.disabled = false; listar(); }
      }
      function listar() {
        const termo = normalizar(busca.value.trim());
        const vozes = dados.vozes.filter((v) => (!genero.value || (genero.value === "?" ? !v.genero : v.genero === genero.value)) &&
          (!sotaque.value || (sotaque.value === "?" ? !sotaqueDaVoz(v) : sotaqueDaVoz(v) === sotaque.value)) &&
          (!termo || normalizar([v.nome, v.id, v.descricao, v.idade, sotaqueDaVoz(v), rotuloIdioma(v.idioma)].join(" ")).includes(termo)))
          .sort((a, b) => (b.id === atual) - (a.id === atual) || (b.idioma === l.idioma_catalogo) - (a.idioma === l.idioma_catalogo));
        resumo.textContent = `${plural(vozes.length, "voz encontrada", "vozes encontradas")} · Idioma e sotaque são informações distintas.`;
        lista.replaceChildren(...vozes.slice(0, limite).map((v) => {
          const descricao = v.descricao || v.nome.split(" - ").slice(1).join(" - ");
          const meta = [NOMES_GENERO[v.genero] || v.genero || "Gênero não informado", `Idade: ${v.idade || "não informada"}`,
            `Sotaque: ${sotaqueDaVoz(v) || "não informado"}${!v.sotaque && sotaqueDaVoz(v) ? " (no nome)" : ""}`, rotuloIdioma(v.idioma)];
          return h("li", { class: `escolha-voz${v.id === atual ? " atual" : ""}` },
            v.amostra ? botaoTocar(`voz:${v.id}`, v.amostra, `amostra de ${v.nome}`, {
              item: faixaVoz(v), fila: () => vozes.filter((voz) => voz.amostra).map(faixaVoz),
            }) : h("span", { class: "tocar-vazio" }),
            h("div", { class: "escolha-detalhes" }, h("strong", {}, v.nome), h("p", { class: "voz-meta" }, meta.join(" · ")),
              descricao ? h("p", {}, descricao) : null),
            h("button", { class: "botao", type: "button", disabled: salvando || (v.id === atual && !!l.mapa_vozes[personagem]),
              "aria-label": `Selecionar ${v.nome} para ${personagem}`, onclick: () => selecionar(v) }, v.id === atual ? (l.mapa_vozes[personagem] ? "Selecionada" : "Usar esta voz") : "Selecionar"));
        }));
        if (!vozes.length) lista.append(h("li", { class: "catalogo-vazio" }, "Nenhuma voz encontrada. Tente mudar a busca ou os filtros."));
        if (vozes.length > limite) lista.append(h("li", { class: "catalogo-mais" }, h("button", { class: "botao", type: "button",
          onclick: () => { limite += LOTE; listar(); } }, "Mostrar mais vozes")));
      }
      for (const [campo, evento] of [[busca, "input"], [genero, "change"], [sotaque, "change"]]) campo.addEventListener(evento, () => { limite = LOTE; listar(); });
      corpo.replaceChildren(h("div", { class: "filtros" }, busca, genero, sotaque),
        h("div", { class: "barra-selecao" }, resumo, h("button", { class: "botao sutil", type: "button", onclick: () => {
          corpo.replaceChildren(h("p", { role: "status" }, "Atualizando catálogo…")); montar(true);
        } }, "Atualizar catálogo")), erro, lista);
      listar();
      busca.focus();
    } catch (e) {
      if (modal.open) corpo.replaceChildren(h("p", { role: "alert" }, `Não foi possível carregar o catálogo: ${e.message}`),
        h("button", { class: "botao", type: "button", onclick: () => montar(atualizar) }, "Tentar novamente"));
    }
  }
  montar();
}

function telaCatalogo(l) {
  const raiz = h("div", {});
  const pronto = estado.catalogo[l.provedor];
  if (pronto) {
    montarCatalogo(raiz, l, pronto);
  } else {
    raiz.append(h("div", { class: "vazio" }, `Buscando as vozes do ${l.provedor}…`));
    carregarCatalogo(l.provedor).then((d) => montarCatalogo(raiz, l, d)).catch((e) => raiz.replaceChildren(
      h("div", { class: "vazio" }, h("h2", {}, "Não deu para listar as vozes"), e.message)));
  }
  return raiz;
}

async function carregarCatalogo(provedor, atualizar = false) {
  const d = await api(`/api/catalogo/${provedor}${atualizar ? "?atualizar=true" : ""}`);
  estado.catalogo[provedor] = d;
  return d;
}

function montarCatalogo(raiz, l, dados) {
  const f = estado.filtro;
  if (f.idioma == null) f.idioma = dados.vozes.some((v) => v.idioma === l.idioma_catalogo) ? l.idioma_catalogo : "";

  const usos = {};  // voice_id -> personagens que usam a voz no livro.yaml
  for (const [p, id] of Object.entries(l.mapa_vozes)) (usos[id] ||= []).push(p);

  const porIdioma = {};
  dados.vozes.forEach((v) => (porIdioma[v.idioma] = (porIdioma[v.idioma] || 0) + 1));
  const idiomas = Object.entries(porIdioma).sort((a, b) => b[1] - a[1]);

  let limite = LOTE;
  const lista = h("ul", { class: "catalogo" });
  const resumo = h("span", {});

  function filtradas() {
    const busca = f.busca.trim().toLowerCase();
    return dados.vozes.filter((v) =>
      (!f.idioma || v.idioma === f.idioma || (f.multilingue && v.idioma === "Multilingual")) &&
      (!f.genero || v.genero === f.genero) &&
      (!busca || v.nome.toLowerCase().includes(busca) || v.id.startsWith(busca)));
  }

  function atualizar() {
    // As do idioma escolhido antes das multilíngues.
    const vozes = filtradas().sort((a, b) => (a.idioma === "Multilingual") - (b.idioma === "Multilingual"));
    resumo.textContent = plural(vozes.length, "voz", "vozes");
    lista.replaceChildren(...vozes.slice(0, limite).map(linhaVoz));
    if (!vozes.length) lista.append(h("li", { class: "catalogo-vazio" }, "Nenhuma voz com esses filtros."));
    if (vozes.length > limite) {
      lista.append(h("li", { class: "catalogo-mais" }, h("button", {
        class: "botao", type: "button", onclick: () => { limite += LOTE; atualizar(); },
      }, `Mostrar mais ${Math.min(LOTE, vozes.length - limite)}`)));
    }
  }

  function linhaVoz(v) {
    const [nome, ...descricao] = v.nome.split(" - ");
    const quem = usos[v.id] || [];
    return h("li", { class: "voz-linha" },
      v.amostra ? botaoTocar(`voz:${v.id}`, v.amostra, `amostra de ${nome}`, {
        item: faixaVoz(v), fila: () => filtradas().sort((a, b) => (a.idioma === "Multilingual") - (b.idioma === "Multilingual"))
          .filter((voz) => voz.amostra).map(faixaVoz),
      }) : h("span", { class: "tocar-vazio" }),
      h("div", { class: "voz-nome" },
        h("strong", {}, nome),
        descricao.length ? h("span", {}, descricao.join(" - ")) : null),
      h("span", { class: "voz-meta" }, [NOMES_GENERO[v.genero] ?? v.genero, rotuloIdioma(v.idioma)].filter(Boolean).join(", ")),
      h("div", { class: "voz-uso" }, quem.map((p) => h("span", { class: "uso" },
        h("span", { class: "amostra", style: { "--cor": corDe(p) } }), p))),
      h("button", {
        class: "botao sutil copiar", type: "button", title: v.id,
        onclick: () => navigator.clipboard.writeText(v.id).then(
          () => avisar(`voice_id de ${nome} copiado. Cole em vozes > ${l.provedor} no livro.yaml`),
          () => avisar(`Não deu para copiar. O voice_id é ${v.id}`, true)),
      }, "Copiar id"),
    );
  }

  const mudar = (campo) => (e) => {
    f[campo] = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    limite = LOTE;
    multi.disabled = !f.idioma || f.idioma === "Multilingual";
    atualizar();
  };
  const multi = h("input", { type: "checkbox", checked: f.multilingue, onchange: mudar("multilingue") });
  multi.disabled = !f.idioma || f.idioma === "Multilingual";
  const atualizarLista = h("button", {
    class: "botao sutil", type: "button", title: "A lista fica guardada por um dia",
    onclick: async (e) => {
      e.target.disabled = true;
      try {
        await carregarCatalogo(l.provedor, true);
        render();
        avisar("Lista de vozes atualizada");
      } catch (erro) {
        e.target.disabled = false;
        avisar(erro.message, true);
      }
    },
  }, "Buscar de novo");

  // As vozes do livro.yaml ficam sempre à vista, fora dos filtros (podem ser de outro idioma).
  const porId = Object.fromEntries(dados.vozes.map((v) => [v.id, v]));
  const emUso = Object.keys(usos).map((id) => porId[id] || { id, nome: id, idioma: "", genero: "", amostra: null });

  raiz.replaceChildren(
    emUso.length ? h("section", { class: "em-uso" },
      h("h3", {}, "Em uso neste livro"),
      h("ul", { class: "catalogo" }, emUso.map(linhaVoz)),
    ) : null,
    h("h3", { class: "titulo-secao" }, `Vozes do ${l.provedor}`),
    h("div", { class: "filtros" },
      h("input", {
        type: "search", class: "campo busca", placeholder: "Buscar por nome ou id", value: f.busca,
        "aria-label": "Buscar voz", oninput: mudar("busca"),
      }),
      h("select", { class: "campo", "aria-label": "Idioma", onchange: mudar("idioma") },
        h("option", { value: "", selected: !f.idioma }, `Todos os idiomas (${dados.vozes.length})`),
        idiomas.map(([i, n]) => h("option", { value: i, selected: f.idioma === i }, `${rotuloIdioma(i)} (${n})`))),
      h("select", { class: "campo", "aria-label": "Gênero", onchange: mudar("genero") },
        h("option", { value: "" }, "Qualquer gênero"),
        Object.entries(NOMES_GENERO).map(([g, rotulo]) => h("option", { value: g, selected: f.genero === g }, rotulo))),
      h("label", { class: "marcar" }, multi, "Incluir multilíngues"),
    ),
    h("div", { class: "barra-selecao" },
      resumo,
      h("span", {}, `Lista de ${new Date(dados.buscado_em * 1000).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}`, atualizarLista),
    ),
    lista,
    h("p", { class: "dica" },
      "As amostras vêm do site do ", l.provedor, " e não gastam crédito. Para usar uma voz, copie o id e cole em ",
      h("strong", {}, `vozes > ${l.provedor}`), " na ",
      h("button", { class: "botao sutil", type: "button", onclick: () => ir(estado.slug, "config") }, "configuração"), "."),
  );
  atualizar();
}

// ---------- vídeos ----------

const tempoVideo = (segundos) => {
  const n = Math.max(0, Math.floor(segundos || 0));
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
};
const dataLocal = (data) => {
  const d = new Date(data?.replace(" ", "T"));
  return Number.isNaN(d.getTime()) ? "após a renovação" : d.toLocaleString("pt-BR");
};

function atualizarVideos() { estado.videos = null; render(); }

function telaVideos(l) {
  const raiz = h("div", { class: "videos" });
  const slug = l.slug;
  if (!estado.videos || estado.videos.slug !== slug) {
    raiz.append(h("p", { class: "vazio" }, "Carregando vídeos e avatares…"));
    api(`/api/livros/${slug}/videos`).then((dados) => {
      if (estado.slug !== slug || estado.aba !== "videos") return;
      estado.videos = { slug, ...dados };
      render();
    }).catch((erro) => raiz.replaceChildren(h("p", { class: "erro-campo" }, erro.message),
      h("button", { class: "botao", onclick: atualizarVideos }, "Tentar novamente")));
    return raiz;
  }
  const dados = estado.videos;
  const ocupado = !!estado.tarefa;
  const chave = { provedor: "huggingface", rotulo: "Hugging Face", final: dados.hf.final,
    link_chave: "https://huggingface.co/settings/tokens" };
  const quota = h("p", { class: "dica", role: "status" }, "A cota e o limite de execuções são conferidos durante a geração.");
  const conferir = h("button", { class: "botao", type: "button", disabled: !dados.hf.configurado,
    onclick: async () => {
      conferir.disabled = true;
      quota.textContent = "Conferindo a cota…";
      try {
        const d = await api("/api/video/huggingface?atualizar=true");
        quota.textContent = d.aviso || (d.cota ? `${tempoVideo(d.cota.restante_segundos)} de processamento disponíveis. Renovação: ${dataLocal(d.cota.renova_em)}.` : "Configure o token do Hugging Face.");
      } catch (e) { quota.textContent = e.message; }
      finally { conferir.disabled = false; }
    } }, "Conferir cota gratuita");
  const comAvatar = dados.personagens.filter((p) => p.avatar).length;
  raiz.append(h("section", { class: "video-config" },
    h("div", {}, h("h2", {}, "Avatares e conta"),
      h("p", { class: "dica" }, "Cada personagem aparece com o seu avatar, e os avatares são só deste livro. Ao gerar um capítulo, escolha ou crie o avatar de cada personagem que fala nele."),
      h("p", { class: "dica" }, `${comAvatar} de ${plural(dados.personagens.length, "personagem tem", "personagens têm")} avatar neste livro.`),
      h("div", { class: "acoes" },
        h("button", { class: "botao", type: "button", onclick: () => pedirChave(chave) }, dados.hf.configurado ? "Trocar token Hugging Face" : "Configurar token Hugging Face"), conferir), quota)));
  raiz.append(h("p", { class: "dica" }, "O modo gratuito gera trechos curtos e para quando atinge os limites. Para continuar em outro dia, clique em Retomar. O capítulo final fica disponível quando todos os trechos terminarem."));
  const donos = Object.fromEntries(dados.personagens.map((p) => [p.personagem, p.avatar]));
  raiz.append(h("div", { class: "video-lista" }, dados.capitulos.map((c) => {
    const pct = c.total ? Math.min(100, c.segundos / c.total * 100) : 0;
    const pausado = c.situacao === "aguardando_cota";
    const rotulo = c.final ? "Vídeo completo" : pausado ? "Aguardando renovação dos limites" : c.segundos ? "Geração iniciada" : "Ainda sem vídeo";
    const url = `/api/livros/${slug}/videos/${c.cap}/arquivo${c.final ? "" : "?parcial=true"}`;
    return h("section", { class: "video-card" },
      h("div", { class: "video-card-topo" }, h("div", {}, h("h3", {}, nomeCap(c.cap)),
        h("p", { class: c.final ? "ok" : pausado ? "atencao" : "dica" }, c.tem_audio ? rotulo : "O áudio será gerado a partir do roteiro")),
        h("button", { class: "botao primario", type: "button", disabled: ocupado || !dados.hf.configurado || !c.personagens.length || c.final,
          onclick: () => iniciarVideo(c) }, c.final ? "Concluído" : iniciado(c) ? "Retomar vídeo" : !c.tem_audio ? "Gerar áudio e vídeo" : "Gerar vídeo")),
      h("progress", { max: 100, value: pct, "aria-label": `Progresso do vídeo do ${nomeCap(c.cap)}` }),
      h("p", { class: "video-tempo" }, `${tempoVideo(c.segundos)} de ${c.total == null ? "—" : tempoVideo(c.total)} · ${pct.toFixed(1)}%`,
        c.avatar_unico ? " · Avatar único (começou antes dos avatares por personagem)" : ""),
      c.personagens.length ? elenco(slug, c.personagens, donos) : null,
      c.aviso ? h("div", { class: "video-aviso" }, h("p", { class: "atencao" }, c.aviso.replace(/^cap_\d+:\s*/, "").replace(/^./, (x) => x.toUpperCase())),
        h("button", { class: "botao", type: "button", disabled: ocupado, onclick: () => rodar("sintetizar", [c.cap]) }, "Gerar áudio para o vídeo")) : null,
      pausado && c.cota?.renova_em ? h("p", { class: "dica" }, `Renovação do tempo de GPU: ${dataLocal(c.cota.renova_em)}. O limite de execuções também precisa estar disponível.`) : null,
      c.situacao === "interrompido" || c.situacao === "erro" ? h("p", { class: "erro-campo" }, c.motivo || "A geração foi interrompida. Os trechos prontos estão salvos.") : null,
      c.final || c.parcial ? [
        h("strong", { class: "video-rotulo" }, c.final ? "Capítulo completo" : "Prévia parcial do início do capítulo"),
        h("video", { controls: true, preload: "none", src: url }),
        h("a", { class: "botao", href: url, download: `${c.cap}${c.final ? "" : "-parcial"}.mp4` }, c.final ? "Baixar capítulo" : "Baixar prévia parcial"),
      ] : null);
  })));
  return raiz;
}

// Já tem trecho pedido ao Hugging Face: retoma com os avatares de quando começou.
// Rosto do personagem no elenco: a foto do avatar com um anel na cor dele, ou a silhueta tracejada.
function rosto(slug, personagem, avatarId, classe = "") {
  const estilo = { "--cor": corDe(personagem) };
  return avatarId
    ? h("img", { class: `rosto ${classe}`, style: estilo, src: `/api/livros/${slug}/videos/avatares/${avatarId}`, alt: "" })
    : h("span", { class: `rosto sem-rosto ${classe}`, style: estilo, "aria-hidden": "true" }, personagem.slice(0, 1).toUpperCase());
}

function elenco(slug, nomes, donos) {
  const visiveis = nomes.slice(0, 10);
  const resto = nomes.length - visiveis.length;
  const prontos = nomes.filter((n) => donos[n]).length;
  return h("div", { class: "elenco" },
    h("ul", { class: "elenco-rostos", "aria-label": "Elenco do capítulo" },
      visiveis.map((n) => h("li", { title: `${n}${donos[n] ? "" : " (sem avatar)"}` }, rosto(slug, n, donos[n]),
        h("span", { class: "so-leitor" }, `${n}${donos[n] ? "" : ", sem avatar"}`))),
      resto > 0 ? h("li", { class: "elenco-mais" }, `+${resto}`) : null),
    h("span", { class: prontos === nomes.length ? "elenco-conta ok" : "elenco-conta" },
      prontos === nomes.length ? "Elenco completo" : `${prontos} de ${plural(nomes.length, "personagem", "personagens")} com avatar`));
}

const iniciado = (c) => c.avatar_unico || c.segundos > 0 || ["gerando", "aguardando_cota", "interrompido", "montando"].includes(c.situacao);

async function recarregarVideos(slug) {
  const dados = await api(`/api/livros/${slug}/videos`);
  if (estado.slug === slug) estado.videos = { slug, ...dados };
  return estado.videos;
}

// Lista quem fala no capítulo; cada personagem escolhe um avatar do livro ou cria um novo.
function escolherAvatares(cap) {
  const slug = estado.slug;
  const ok = $("dialogo-ok");
  const lista = h("div", { class: "avatar-lista" });
  const resumo = h("p", { class: "avatar-resumo", role: "status" });
  const erro = h("p", { class: "erro-campo", role: "alert", hidden: true });
  const falhar = (e) => { erro.textContent = e.message; erro.hidden = false; };
  // Redesenhar troca os elementos: o foco volta para a mesma linha, não para o começo da página.
  const focarLinha = (nome, alvo) => [...lista.children].find((l) => l.dataset.personagem === nome)?.querySelector(alvo)?.focus();

  function desenhar() {
    const dados = estado.videos;
    const dono = Object.fromEntries(dados.personagens.map((p) => [p.personagem, p.avatar]));
    lista.replaceChildren(...cap.personagens.map((nome) => {
      const atual = dono[nome];
      const livres = dados.avatares.filter((a) => !a.personagem || a.personagem === nome);
      const escolha = h("select", { class: "campo", "aria-label": `Avatar de ${nome}`, disabled: !livres.length,
        onchange: async (e) => {
          if (!e.target.value) return;
          try {
            await api(`/api/livros/${slug}/videos/personagens/${encodeURIComponent(nome)}`, { method: "PUT", body: JSON.stringify({ avatar: e.target.value }) });
            erro.hidden = true;
            await recarregarVideos(slug);
            desenhar();
          } catch (err) { falhar(err); desenhar(); }
          focarLinha(nome, "select");
        } },
        h("option", { value: "" }, livres.length ? "Escolher um avatar existente" : "Nenhum avatar livre neste livro"),
        livres.map((a) => h("option", { value: a.id, selected: a.id === atual }, a.personagem ? `${a.nome}, avatar de ${a.personagem}` : `${a.nome}, sem personagem`)));
      return h("div", { class: "avatar-linha", "data-personagem": nome, style: { "--cor": corDe(nome) } },
        rosto(slug, nome, atual, "grande"),
        h("div", { class: "avatar-campos" }, h("strong", { class: "avatar-nome" }, nome),
          h("div", { class: "avatar-controles" }, escolha,
            h("button", { class: "botao", type: "button", onclick: async () => {
              if (await formularioAvatar(slug, nome)) { erro.hidden = true; await recarregarVideos(slug); desenhar(); }
              focarLinha(nome, "button");
            } }, atual ? "Criar outro avatar" : "Criar novo avatar"))));
    }));
    const faltam = cap.personagens.filter((nome) => !dono[nome]).length;
    resumo.textContent = faltam ? `Falta avatar para ${plural(faltam, "personagem", "personagens")}.` : "Todos têm avatar. Pode gerar.";
    ok.disabled = cap.personagens.some((nome) => !dono[nome]);
  }

  desenhar();
  const fechado = confirmar(`Avatares do ${nomeCap(cap.cap)}`, [
    h("p", {}, `${plural(cap.personagens.length, "personagem fala", "personagens falam")} neste capítulo. Cada um precisa de um avatar próprio deste livro.`),
    lista, resumo, erro,
    !cap.tem_audio ? h("p", { class: "atencao" }, `${plural(cap.falas_novas || 0, "fala nova será gerada", "falas novas serão geradas")} no ${estado.livro.provedor}. A síntese de voz consome créditos do provedor. Depois, o vídeo será gerado automaticamente.`) : null,
    h("p", {}, "As fotos e os trechos do áudio serão enviados à demo pública SadTalker no Hugging Face, usando só a cota gratuita."),
  ], "Gerar com a cota disponível");
  $("dialogo").classList.add("largo");
  return fechado.finally(() => { ok.disabled = false; $("dialogo").classList.remove("largo"); });
}

// Tela inteira para criar o avatar de um personagem: ficha + imagens enviadas ou criadas com IA.
// Resolve true quando o avatar foi salvo.
function formularioAvatar(slug, personagem) {
  const dados = estado.videos;
  const info = dados.personagens.find((p) => p.personagem === personagem) || {};
  const imagens = [];  // {b64, url, origem}
  let principal = 0;
  const modal = h("dialog", { class: "modal-cheio", "aria-labelledby": "modal-avatar-titulo" });
  const erro = h("p", { class: "erro-campo", role: "alert", hidden: true });
  const status = h("p", { class: "dica", role: "status" });
  const falhar = (e) => { erro.textContent = e.message; erro.hidden = false; status.textContent = ""; };

  const nome = h("input", { class: "campo", value: personagem, maxlength: 200, required: true });
  const idade = h("input", { class: "campo", placeholder: "ex.: 35, adolescente, idoso", maxlength: 50 });
  const descricao = h("textarea", { class: "campo", rows: 5, maxlength: 2000,
    placeholder: "Aparência, roupa, jeito… quanto mais concreto, melhor a imagem." });
  const voz = h("input", { class: "campo", value: info.voz || "", readonly: true,
    title: "A voz vem do livro.yaml; troque-a na aba Vozes." });
  const ia = h("select", { class: "campo", "aria-label": "IA" },
    h("option", { value: "openai" }, "OpenAI (recomendado)"),
    h("option", { value: "claude" }, "Claude escreve o pedido · OpenAI desenha"));
  const palco = h("div", { class: "palco", style: { "--cor": corDe(personagem) } });
  const galeria = h("ul", { class: "galeria", "aria-label": "Imagens do avatar" });
  const contador = h("p", { class: "dica" });
  const arquivos = h("input", { type: "file", accept: "image/png,image/jpeg", multiple: true, hidden: true, "aria-label": "Imagens do avatar" });
  const salvar = h("button", { class: "botao primario", type: "button" }, "Salvar avatar");
  const criarIA = h("button", { class: "botao gravar", type: "button" }, "Criar imagem com IA");
  const descrever = h("button", { class: "botao sutil", type: "button" }, "Descrever pelas imagens");
  const chaves = h("div", { class: "chaves-ia" });

  const ficha = () => ({ personagem, nome: nome.value.trim(), idade: idade.value.trim(), descricao: descricao.value.trim(), voz: voz.value });
  function atualizar() {
    const atual = imagens[principal];
    palco.replaceChildren(atual
      ? h("img", { src: atual.url, alt: `Imagem principal do avatar de ${personagem}` })
      : h("div", { class: "palco-vazio" }, rosto(slug, personagem, null, "enorme"),
          h("p", {}, "A imagem principal aparece aqui. Rosto de frente, ombros para cima, funciona melhor no vídeo.")));
    galeria.replaceChildren(...imagens.map((img, i) => h("li", { class: `miniatura${i === principal ? " principal" : ""}` },
      h("button", { class: "miniatura-escolher", type: "button", "aria-pressed": String(i === principal),
        "aria-label": `Usar a imagem ${i + 1} (${img.origem}) como principal`, onclick: () => { principal = i; atualizar(); } },
        h("img", { src: img.url, alt: "" })),
      i === principal ? h("span", { class: "miniatura-selo", "aria-hidden": "true" }, "Principal") : null,
      h("button", { class: "miniatura-remover", type: "button", "aria-label": `Remover a imagem ${i + 1}`,
        onclick: () => { imagens.splice(i, 1); principal = Math.min(principal, Math.max(0, imagens.length - 1)); atualizar(); } }, "×"))));
    contador.textContent = imagens.length ? `${plural(imagens.length, "imagem", "imagens")} de 8. Clique numa miniatura para torná-la principal.` : "Nenhuma imagem ainda.";
    salvar.disabled = !imagens.length || !nome.value.trim();
    descrever.disabled = !imagens.length;
    const sit = estado.videos.ia || {};
    criarIA.disabled = !sit.openai?.configurado || imagens.length >= 8;
    chaves.replaceChildren(...[["openai", "OpenAI", "da", "https://platform.openai.com/api-keys"], ["claude", "Claude", "do", "https://console.anthropic.com/settings/keys"]]
      .filter(([k]) => !sit[k]?.configurado).map(([k, rotulo, art, link]) => {
        const campo = h("input", { class: "campo", type: "password", autocomplete: "off", placeholder: `Chave ${art} ${rotulo}`, "aria-label": `Chave ${art} ${rotulo}` });
        return h("div", { class: "chave-ia" }, h("span", {}, `${rotulo} sem chave. `, h("a", { href: link, target: "_blank", rel: "noopener" }, "Pegar chave")),
          campo, h("button", { class: "botao", type: "button", onclick: async () => {
            try {
              status.textContent = `Conferindo a chave ${art} ${rotulo}…`;
              await api(`/api/chaves/${k}`, { method: "PUT", body: JSON.stringify({ chave: campo.value }) });
              await recarregarVideos(slug);
              status.textContent = `Chave ${art} ${rotulo} salva.`;
              erro.hidden = true;
              atualizar();
            } catch (e) { falhar(e); }
          } }, "Salvar chave"));
      }));
  }

  async function ocupado(botao, texto, trabalho) {
    const antes = botao.textContent;
    botao.disabled = true; botao.textContent = texto; erro.hidden = true;
    try { await trabalho(); } catch (e) { falhar(e); } finally { botao.textContent = antes; atualizar(); }
  }
  const referencias = () => imagens.map((i) => i.b64);

  arquivos.addEventListener("change", async () => {
    for (const f of [...arquivos.files]) {
      if (imagens.length >= 8) { falhar(new Error("Até 8 imagens por avatar.")); break; }
      if (!/^image\/(png|jpeg)$/.test(f.type)) { falhar(new Error(`${f.name}: use PNG ou JPEG.`)); continue; }
      if (f.size > 10000000) { falhar(new Error(`${f.name}: a imagem deve ter até 10 MB.`)); continue; }
      const b64 = await arquivoBase64(f);
      imagens.push({ b64, url: `data:${f.type};base64,${b64}`, origem: "Enviada" });
    }
    arquivos.value = "";
    atualizar();
  });
  criarIA.addEventListener("click", () => ocupado(criarIA, "Criando imagem… (pode levar 1 min)", async () => {
    status.textContent = imagens.length ? "Usando as imagens como referência." : "";
    const r = await api(`/api/livros/${slug}/videos/avatares/imagem-ia`, { method: "POST",
      body: JSON.stringify({ ...ficha(), referencias: referencias(), ia: ia.value }) });
    imagens.push({ b64: r.conteudo, url: `data:image/png;base64,${r.conteudo}`, origem: ia.value === "claude" ? "IA (Claude + OpenAI)" : "IA (OpenAI)" });
    principal = imagens.length - 1;
    status.textContent = `Imagem criada e definida como principal. Pedido usado: ${r.pedido}`;
  }));
  descrever.addEventListener("click", () => ocupado(descrever, "Descrevendo…", async () => {
    const qual = ia.value === "claude" ? "claude" : "openai";
    const r = await api(`/api/livros/${slug}/videos/avatares/descrever`, { method: "POST",
      body: JSON.stringify({ ...ficha(), referencias: referencias(), ia: qual }) });
    descricao.value = r.descricao;
  }));
  nome.addEventListener("input", atualizar);

  return new Promise((resolve) => {
    let salvo = false;
    salvar.addEventListener("click", () => ocupado(salvar, "Salvando…", async () => {
      await api(`/api/livros/${slug}/videos/avatares`, { method: "POST",
        body: JSON.stringify({ ...ficha(), imagens: referencias(), principal }) });
      salvo = true;
      modal.close();
    }));
    modal.addEventListener("close", () => { modal.remove(); resolve(salvo); }, { once: true });
    modal.append(
      h("header", { class: "modal-topo" }, h("div", { class: "modal-faixa" },
        h("div", { class: "modal-titulo" }, rosto(slug, personagem, null, "medio"),
          h("div", {}, h("h2", { id: "modal-avatar-titulo" }, `Avatar de ${personagem}`),
            h("p", { class: "dica" }, "Só deste livro e só deste personagem."))),
        h("button", { class: "botao sutil", type: "button", onclick: () => modal.close() }, "Fechar"))),
      h("div", { class: "modal-corpo" }, h("div", { class: "modal-faixa modal-colunas" },
        h("section", { class: "modal-ficha", "aria-labelledby": "ficha-titulo" },
          h("h3", { id: "ficha-titulo" }, "Ficha"),
          h("label", {}, h("span", {}, "Nome"), nome),
          h("label", {}, h("span", {}, "Idade"), idade),
          h("label", {}, h("span", {}, "Voz"), voz, h("small", { class: "dica" }, "A do livro. Para trocar, use a aba Vozes.")),
          h("label", {}, h("span", {}, "Descrição"), descricao),
          h("div", { class: "acoes" }, descrever)),
        h("section", { class: "modal-imagens", "aria-labelledby": "imagens-titulo" },
          h("h3", { id: "imagens-titulo" }, "Imagens"),
          palco, contador, galeria,
          h("div", { class: "acoes" },
            h("button", { class: "botao", type: "button", onclick: () => arquivos.click() }, "Enviar imagens"), arquivos),
          h("div", { class: "painel-ia" },
            h("h3", {}, "Criar imagem com IA"),
            h("p", { class: "dica" }, "A OpenAI desenha a partir da ficha e usa as imagens acima como referência. Com o Claude, ele olha as imagens e escreve o pedido, e a OpenAI desenha. Gasta crédito do provedor."),
            h("label", {}, h("span", {}, "Quem cria"), ia),
            chaves,
            h("div", { class: "acoes" }, criarIA)),
          status, erro))),
      h("footer", { class: "modal-rodape" }, h("div", { class: "modal-faixa modal-faixa-fim" },
        h("button", { class: "botao", type: "button", onclick: () => modal.close() }, "Cancelar"), salvar)),
    );
    document.body.append(modal);
    atualizar();
    modal.showModal();
    nome.focus();
  });
}

async function iniciarVideo(cap) {
  const slug = estado.slug;
  if (cap.aviso && !iniciado(cap)) { avisar(cap.aviso, true); return; }
  const ok = iniciado(cap)
    ? await confirmar(`Retomar o vídeo do ${nomeCap(cap.cap)}?`, [
      h("p", {}, "Continua de onde parou, com os mesmos avatares, usando a cota gratuita disponível. Não compra créditos nem contrata hardware."),
    ], "Retomar com a cota disponível")
    : await escolherAvatares(cap);
  if (!ok || estado.slug !== slug) return;
  estado.tarefa = { etapa: "video", livro: slug, total: cap.total || 0, feitas: cap.segundos || 0 };
  render();
  try {
    const r = await api(`/api/livros/${slug}/videos/tarefas`, { method: "POST", body: JSON.stringify({ cap: cap.cap, gerar_audio: !cap.tem_audio }) });
    acompanhar(r.desde);
  } catch (e) { estado.tarefa = null; render(); avisar(e.message, true); }
}

// ---------- configuração ----------

function telaConfig() {
  const salvar = h("button", { class: "botao primario", type: "button", disabled: true, onclick: () => salvarConfig() }, "Salvar livro.yaml");
  const area = h("textarea", {
    class: "roteiro codigo", spellcheck: "false", "aria-label": "livro.yaml", disabled: true,
    oninput: () => { estado.sujo = true; salvar.disabled = false; },
    onkeydown: (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); if (estado.sujo) salvarConfig(); }
    },
  }, "Carregando…");

  async function salvarConfig() {
    salvar.disabled = true;
    try {
      const r = await api(`/api/livros/${estado.slug}/config`, { method: "PUT", body: JSON.stringify({ texto: area.value }) });
      estado.sujo = false;
      avisar(r.aviso || "livro.yaml salvo e falas separadas", !!r.aviso);
      await Promise.all([carregarLivros(), recarregarLivro()]);
    } catch (e) {
      salvar.disabled = false;
      avisar(e.message, true);
    }
  }

  api(`/api/livros/${estado.slug}/config`).then((r) => { area.value = r.texto; area.disabled = false; });

  return h("div", {},
    h("div", { class: "folha" }, h("div", { class: "folha-topo" }, h("span", {}, `livros/${estado.slug}/livro.yaml`), salvar), area),
    h("p", { class: "dica" },
      "Personagens, apelidos (nome no roteiro → nome com voz) e vozes por provedor. ",
      "O arquivo é conferido antes de salvar; os comentários são mantidos."),
  );
}

// ---------- adicionar livro ----------

function telaNovoVideo() {
  let elenco = [], textoConferido = null, vozes = [];
  const erro = h("p", { class: "erro-campo", role: "alert", hidden: true });
  const falhar = (e) => { erro.textContent = e.message; erro.hidden = false; };
  const titulo = h("input", { class: "campo", required: true, maxlength: 200, "aria-label": "Título do vídeo" });
  const lista = h("div", { class: "avatar-lista" });
  const salvar = h("button", { class: "botao primario", type: "submit", disabled: true }, "Salvar projeto e revisar geração");
  const invalidar = () => {
    estado.sujo = true;
    textoConferido = null;
    salvar.disabled = true;
    lista.replaceChildren(h("p", { class: "dica" }, "Confira os personagens novamente após alterar o roteiro."));
  };
  const roteiro = h("textarea", { class: "campo", rows: 12, maxlength: 1000000, required: true,
    "aria-label": "Roteiro do vídeo", placeholder: "Narrador: Era uma vez…\nAna: Olá!\nBruno: Oi, Ana!", oninput: invalidar });
  const provedor = h("select", { class: "campo", "aria-label": "Provedor das vozes", onchange: () => {
    vozes = [];
    for (const p of elenco) p.voz = "";
    estado.sujo = true;
    desenhar();
  } }, h("option", { value: "heygen" }, "HeyGen"), h("option", { value: "openrouter" }, "OpenRouter"));
  const pronto = () => textoConferido === roteiro.value && elenco.length && elenco.every((p) => p.voz.trim() && p.avatar);
  function desenhar() {
    salvar.disabled = !pronto();
    lista.replaceChildren(...elenco.map((p, i) => {
      const voz = h("input", { class: "campo", value: p.voz, list: `vozes-video-${i}`,
        "aria-label": `Voz de ${p.nome}`, placeholder: "Escolha no catálogo ou cole o ID da voz",
        oninput: (e) => { p.voz = e.target.value; estado.sujo = true; salvar.disabled = !pronto(); } });
      const imagem = h("input", { type: "file", accept: "image/png,image/jpeg", "aria-label": `Avatar de ${p.nome}`,
        onchange: async (e) => {
          const f = e.target.files[0];
          if (!f) return;
          if (f.size > 10000000) { falhar(new Error("Envie uma imagem de até 10 MB.")); return; }
          try { p.avatar = await arquivoBase64(f); p.tipo = f.type; estado.sujo = true; desenhar(); }
          catch (err) { falhar(err); }
        } });
      return h("section", { class: "avatar-linha" },
        p.avatar ? h("img", { class: "rosto grande", src: `data:${p.tipo};base64,${p.avatar}`, alt: `Avatar de ${p.nome}` })
          : h("span", { class: "rosto sem-rosto grande", "aria-hidden": "true" }, p.nome.slice(0, 1)),
        h("div", { class: "avatar-campos" }, h("h3", {}, p.nome), h("p", { class: "dica" }, plural(p.falas, "fala", "falas")),
          h("label", {}, "Voz", voz),
          h("datalist", { id: `vozes-video-${i}` }, vozes.map((v) => h("option", { value: provedor.value === "heygen" ? v.id : v.nome }, `${v.nome} · ${v.idioma}`))),
          h("label", {}, "Foto do personagem (PNG ou JPEG, de frente)", imagem)));
    }));
  }
  const arquivo = h("input", { type: "file", accept: ".txt,.md", "aria-label": "Enviar roteiro",
    onchange: async (e) => {
      const f = e.target.files[0];
      if (!f) return;
      if (f.size > 1000000) { falhar(new Error("Envie um roteiro de até 1 MB.")); return; }
      try { roteiro.value = await f.text(); invalidar(); }
      catch (err) { falhar(err); }
    } });
  const conferir = h("button", { class: "botao", type: "button", onclick: async () => {
    conferir.disabled = true;
    erro.hidden = true;
    const texto = roteiro.value;
    try {
      const r = await api("/api/video/roteiro", { method: "POST", body: JSON.stringify({ texto }) });
      if (texto !== roteiro.value) return;
      const anteriores = new Map(elenco.map((p) => [p.nome, p]));
      elenco = r.personagens.map((p) => ({ voz: "", avatar: null, ...anteriores.get(p.nome), ...p }));
      textoConferido = texto;
      desenhar();
    } catch (err) { falhar(err); }
    finally { conferir.disabled = false; }
  } }, "Identificar personagens");
  const catalogo = h("button", { class: "botao", type: "button", onclick: async () => {
    catalogo.disabled = true;
    const escolhido = provedor.value;
    try {
      const d = await obterCatalogo("heygen");
      if (provedor.value === escolhido) { vozes = d.vozes; desenhar(); }
    } catch (err) { falhar(err); }
    finally { catalogo.disabled = false; }
  } }, "Carregar catálogo de vozes");
  $("principal").replaceChildren(h("h1", {}, "Criar vídeo do roteiro"),
    h("p", { class: "dica" }, "Envie o roteiro e a foto de cada personagem. O aplicativo gera as vozes e anima os rostos com a fala sincronizada."),
    h("form", { class: "novo-video painel", onsubmit: async (e) => {
      e.preventDefault();
      if (!pronto()) return;
      salvar.disabled = true;
      try {
        const r = await api("/api/video/projetos", { method: "POST", body: JSON.stringify({
          titulo: titulo.value, texto: roteiro.value, provedor: provedor.value,
          personagens: elenco.map(({ nome, voz, avatar }) => ({ nome, voz, avatar })),
        }) });
        estado.sujo = false;
        await carregarLivros().catch(() => {});
        ir(r.slug, "videos");
      } catch (err) { falhar(err); salvar.disabled = !pronto(); }
    } },
    h("label", {}, "Título do vídeo", titulo),
    h("h2", {}, "1. Roteiro"), arquivo,
    h("p", { class: "dica" }, "Use Nome: fala, uma fala por linha ou parágrafo. Texto sem nome será lido pelo Narrador. Use nomes com iniciais maiúsculas e até 30 caracteres."), roteiro, conferir,
    h("h2", {}, "2. Personagens, vozes e avatares"), h("label", {}, "Provedor das vozes", provedor), catalogo, lista,
    h("p", { class: "dica" }, "Salvar organiza os arquivos e não gera cobranças. Na próxima tela, confira os avatares e confirme Gerar áudio e vídeo. A voz usa créditos; a animação usa a cota disponível no Hugging Face."), erro, salvar));
}

function arquivoBase64(arquivo) {
  return new Promise((resolve, reject) => {
    const leitor = new FileReader();
    leitor.onload = () => resolve(String(leitor.result).split(",")[1]);
    leitor.onerror = () => reject(new Error(`Não foi possível ler ${arquivo.name}`));
    leitor.readAsDataURL(arquivo);
  });
}

function seletorImportacao() {
  const arquivos = h("input", { type: "file", multiple: true, accept: ".md,.txt", "aria-label": "Arquivos de capítulos", hidden: true });
  const pasta = h("input", { type: "file", multiple: true, webkitdirectory: true, "aria-label": "Pasta de capítulos", hidden: true });
  async function escolher(e) {
    const lista = [...e.target.files].filter((f) => /\.(md|txt)$/i.test(f.name));
    if (!lista.length) { avisar("Escolha arquivos .md ou .txt.", true); return; }
    if (lista.length > 500 || lista.reduce((s, f) => s + f.size, 0) > 30000000) {
      avisar("Escolha até 500 arquivos e 30 MB por livro.", true); return;
    }
    const locais = new Map(lista.map((f) => [(f.webkitRelativePath || f.name).replace(/\.(md|txt)$/i, (x) => x.toLowerCase()), f]));
    const nomes = [...locais.keys()].filter((n) => !n.split("/").some((p) => p.startsWith(".")))
      .sort(new Intl.Collator("pt-BR", { numeric: true }).compare);
    const nome = lista[0].webkitRelativePath?.split("/")[0] || "Meu livro";
    await escolherArquivos(null, { caminho: nome, nome, padrao: false, locais,
      arquivos: nomes.map((caminho) => ({ caminho, sugerido: !/^(readme|resumo|licen[cç]a|notas?|indice|índice|sumario|sumário)/i.test(caminho.split("/").at(-1)) })) });
  }
  arquivos.addEventListener("change", escolher);
  pasta.addEventListener("change", escolher);
  return h("section", { class: "importar-computador painel" },
    h("h2", {}, "Importar do computador"),
    h("p", { class: "dica" }, "Escolha capítulos .md ou .txt. Os arquivos ficam guardados junto ao livro, inclusive quando o Dublandio roda no Docker."),
    arquivos, pasta,
    h("div", { class: "acoes" },
      h("button", { class: "botao primario", type: "button", onclick: () => arquivos.click() }, "Escolher arquivos"),
      h("button", { class: "botao", type: "button", onclick: () => pasta.click() }, "Escolher pasta do computador")));
}

// "…/arvore-do-ciclo/05_manuscrito/vol1" -> "Arvore Do Ciclo": pula pastas de organização.
const PASTA_GENERICA = /^(\d+[_-])?(manuscritos?|vol(ume)?s?[_-]?\w*|textos?|capitulos?|capítulos?|livro)$/i;
function tituloDaPasta(caminho) {
  const partes = caminho.split("/").filter(Boolean);
  const nome = [...partes].reverse().find((p) => !PASTA_GENERICA.test(p)) || partes.at(-1) || "";
  return nome.replace(/[_-]+/g, " ").replace(/\b\p{L}/gu, (c) => c.toUpperCase());
}

async function telaNovoLivro(caminho = null) {
  const versao = ++estado.pastaVersao;
  const principal = $("principal");
  principal.replaceChildren(h("div", { class: "vazio" }, "Abrindo pastas…"));
  let pasta;
  try {
    pasta = await api(`/api/pastas${caminho ? `?caminho=${encodeURIComponent(caminho)}` : ""}`);
  } catch (e) {
    if (versao !== estado.pastaVersao || lerHash().slug !== NOVO) return;
    principal.replaceChildren(h("h1", {}, "Adicionar livro"), seletorImportacao(), h("p", { class: "erro-campo" }, e.message));
    return;
  }
  if (versao !== estado.pastaVersao || lerHash().slug !== NOVO) return;
  principal.replaceChildren(
    h("header", { class: "cabecalho" }, h("div", {},
      h("h1", {}, "Adicionar livro"),
      h("div", { class: "cabecalho-sub" }, "Escolha a pasta com os capítulos em .md ou .txt. Os .md são convertidos em roteiro; os .txt já são roteiros e entram como estão."))),
    seletorImportacao(),
    h("h2", { class: "titulo-secao" }, "Ou escolher uma pasta no servidor"),
    h("div", { class: "navegador" },
      h("div", { class: "navegador-topo" },
        pasta.pai ? h("button", { class: "botao sutil", type: "button", onclick: () => telaNovoLivro(pasta.pai) }, "Voltar") : null,
        h("code", { class: "caminho" }, pasta.caminho),
        h("span", { class: "navegador-conta" }, pasta.textos ? plural(pasta.textos, "texto aqui", "textos aqui") : ""),
        h("button", { class: "botao primario", type: "button", onclick: () => escolherArquivos(pasta.caminho) }, "Usar esta pasta"),
      ),
      pasta.pastas.length
        ? h("ul", { class: "pastas" }, pasta.pastas.map((p) => h("li", {},
            h("button", { type: "button", onclick: () => telaNovoLivro(p.caminho) }, h("span", { "aria-hidden": "true" }, "▸ "), p.nome))))
        : h("p", { class: "dica" }, "Nenhuma subpasta."),
    ),
  );
}

async function escolherArquivos(caminho, locais = null) {
  const principal = $("principal");
  const versao = ++estado.pastaVersao;
  let dados;
  try {
    dados = locais || await api(`/api/pastas/textos?caminho=${encodeURIComponent(caminho)}`);
  } catch (e) {
    avisar(e.message, true);
    return;
  }
  if (versao !== estado.pastaVersao || lerHash().slug !== NOVO) return;
  if (!dados.arquivos.length) {
    avisar("Essa pasta não tem nenhum .md ou .txt (nem nas subpastas).", true);
    return;
  }
  // No padrão cap_NNN, os capítulos são os da própria pasta; fora dele, tudo que parece capítulo.
  const marcados = new Set(dados.arquivos.filter((a) =>
    dados.padrao ? /^cap_\d{3}\.(md|txt)$/.test(a.caminho) : a.sugerido).map((a) => a.caminho));
  // Marcados no alto, na ordem; os de fora vão para o fim, para o ↑↓ só mexer nos capítulos.
  const ordem = dados.arquivos.map((a) => a.caminho);
  const reagrupar = () => ordem.sort((a, b) => marcados.has(b) - marcados.has(a));
  reagrupar();

  const titulo = h("input", { class: "campo", value: tituloDaPasta(dados.caminho), required: true, "aria-label": "Título" });
  const provedor = h("select", { class: "campo", "aria-label": "Provedor" },
    h("option", { value: "heygen" }, "HeyGen"), h("option", { value: "openrouter" }, "OpenRouter"));
  const reserva = h("select", { class: "campo", "aria-label": "Reserva" },
    h("option", { value: "openrouter" }, "OpenRouter"), h("option", { value: "heygen" }, "HeyGen"), h("option", { value: "" }, "Nenhuma"));
  provedor.addEventListener("change", () => { reserva.value = provedor.value === "heygen" ? "openrouter" : "heygen"; });
  const personagens = h("input", { class: "campo", placeholder: "Ex.: Dorian, Mireille, Senhora Vell", "aria-label": "Personagens" });
  const lista = h("ol", { class: "arquivos" });
  const resumo = h("span", {});
  const adicionar = h("button", { class: "botao primario", type: "submit" }, "Adicionar livro");
  const erroForm = h("p", { class: "erro-campo", role: "alert", hidden: true });

  function mover(i, delta) {
    const j = i + delta;
    [ordem[i], ordem[j]] = [ordem[j], ordem[i]];
    desenhar();
    lista.querySelectorAll(".arquivo")[j]?.querySelector(delta < 0 ? "[data-subir]" : "[data-descer]")?.focus();
  }

  function desenhar() {
    let n = 0;
    lista.replaceChildren(...ordem.map((a, i) => {
      const marcado = marcados.has(a);
      const cap = marcado ? `cap_${String(++n).padStart(3, "0")}` : "";
      return h("li", { class: marcado ? "arquivo" : "arquivo fora" },
        h("input", {
          type: "checkbox", checked: marcado, "aria-label": `Incluir ${a}`,
          onchange: (e) => {
            if (e.target.checked) {  // entra logo depois do último marcado
              marcados.add(a);
              ordem.splice(ordem.indexOf(a), 1);
              ordem.splice(marcados.size - 1, 0, a);
            } else {
              marcados.delete(a);
              reagrupar();
            }
            desenhar();
          },
        }),
        h("span", { class: "arquivo-cap" }, cap),
        h("span", { class: "arquivo-nome" }, a),
        h("span", { class: "arquivo-ordem" },
          h("button", { class: "botao-icone", type: "button", "data-subir": "", disabled: i === 0, "aria-label": `Subir ${a}`, onclick: () => mover(i, -1) }, "↑"),
          h("button", { class: "botao-icone", type: "button", "data-descer": "", disabled: i === ordem.length - 1, "aria-label": `Descer ${a}`, onclick: () => mover(i, 1) }, "↓")),
      );
    }));
    resumo.textContent = n ? `${plural(n, "capítulo", "capítulos")}, na ordem da lista` : "Marque ao menos um arquivo";
    adicionar.disabled = !n;
  }

  async function enviar(e) {
    e.preventDefault();
    adicionar.disabled = true;
    adicionar.textContent = "Adicionando…";
    erroForm.hidden = true;
    try {
      const selecionados = ordem.filter((a) => marcados.has(a));
      const arquivos = locais ? await Promise.all(selecionados.map(async (nome) => ({ nome, conteudo: await arquivoBase64(locais.locais.get(nome)) }))) : selecionados;
      const r = await api(locais ? "/api/livros/importar" : "/api/livros", {
        method: "POST",
        body: JSON.stringify({
          titulo: titulo.value, origem: dados.caminho, provedor: provedor.value, reserva: reserva.value || null,
          arquivos,
          personagens: personagens.value.split(",").map((p) => p.trim()).filter(Boolean),
        }),
      });
      estado.sujo = false;
      ir(r.slug);
      if (r.aviso) avisar(r.aviso, true);
      if (r.desde != null) {
        estado.tarefa = { etapa: "preparar", livro: r.slug, total: 0, feitas: 0 };
        acompanhar(r.desde);
      }
      await carregarLivros().catch((erro) => avisar(`Livro criado. ${erro.message}`, true));
    } catch (erro) {
      adicionar.disabled = false;
      adicionar.textContent = "Adicionar livro";
      erroForm.textContent = erro.message;
      erroForm.hidden = false;
    }
  }

  principal.replaceChildren(
    h("header", { class: "cabecalho" }, h("div", {},
      h("h1", {}, "Adicionar livro"),
      h("div", { class: "cabecalho-sub" }, h("code", { class: "caminho" }, dados.caminho), "  ",
        h("button", { class: "botao sutil", type: "button", onclick: () => telaNovoLivro(locais ? null : dados.caminho) }, "Trocar pasta")))),
    h("form", { class: "novo-livro", onsubmit: enviar },
      h("div", { class: "campos" },
        h("label", {}, h("span", {}, "Título"), titulo),
        h("label", {}, h("span", {}, "Provedor"), provedor),
        h("label", {}, h("span", {}, "Se a cota acabar, continuar no"), reserva),
        h("label", { class: "largo" }, h("span", {}, "Personagens (opcional, separados por vírgula)"), personagens),
      ),
      h("p", { class: "dica" }, "Os nomes ajudam a descobrir quem fala em cada diálogo. O Narrador começa com a voz Lucian; troque na aba Catálogo depois."),
      h("h3", { class: "titulo-secao" }, "Capítulos"),
      h("div", { class: "barra-selecao" }, resumo),
      lista,
      erroForm,
      h("div", { class: "acoes-form" }, h("a", { class: "botao", href: "#/" }, "Cancelar"), adicionar),
    ),
  );
  desenhar();
  titulo.focus();
}

// ---------- etapas e progresso ----------

async function rodar(etapa, caps = []) {
  const l = estado.livro;
  if (etapa === "sintetizar") {
    const alvo = l.lista.filter((c) => c.tem_manifesto && (!caps.length || caps.includes(c.cap)));
    const novas = alvo.reduce((s, c) => s + c.pendentes, 0);
    const cache = alvo.reduce((s, c) => s + c.falas.length - c.pendentes, 0);
    const comAudio = alvo.filter((c) => c.tem_audio).length;
    const ok = await confirmar(
      `Sintetizar ${plural(alvo.length, "capítulo", "capítulos")}?`,
      [
        novas
          ? h("p", {}, h("strong", {}, plural(novas, "fala nova", "falas novas")), ` serão geradas no ${l.provedor}`,
              l.reserva ? ` (se a cota acabar, continua no ${l.reserva})` : "", ". Isso gasta crédito.")
          : h("p", {}, "Nenhuma fala nova: o áudio é montado só com o que já está em cache."),
        cache ? h("p", {}, `${plural(cache, "fala vem", "falas vêm")} do cache, sem custo.`) : null,
        comAudio ? h("p", {}, `O áudio atual de ${plural(comAudio, "capítulo", "capítulos")} será substituído.`) : null,
      ],
      novas ? `Sintetizar ${plural(novas, "fala", "falas")}` : "Montar áudio",
      { gravar: novas > 0 },
    );
    if (!ok) return;
    estado.tarefa = { etapa, livro: l.slug, total: novas, feitas: 0 };
  } else {
    estado.tarefa = { etapa, livro: l.slug, total: 0, feitas: 0 };
  }
  render();
  try {
    const r = await api(`/api/livros/${l.slug}/tarefas`, { method: "POST", body: JSON.stringify({ etapa, caps }) });
    acompanhar(r.desde);
  } catch (e) {
    estado.tarefa = null;
    render();
    avisar(e.message, true);
  }
}

function abrirPainel(etapa) {
  const painel = $("progresso");
  painel.hidden = false;
  painel.dataset.etapa = etapa;
  delete painel.dataset.fim;
  $("progresso-titulo").textContent = ROTULO_ETAPA[etapa];
  $("progresso-contagem").textContent = "";
  $("progresso-barra").style.width = "0";
  $("progresso-log").replaceChildren();
  $("progresso-fechar").hidden = true;
}

function registrar(texto, classe) {
  const log = $("progresso-log");
  log.append(h("li", { class: classe }, texto));
  while (log.children.length > 200) log.firstChild.remove();
  log.scrollTop = log.scrollHeight;
}

function atualizarContagem() {
  const t = estado.tarefa;
  if (!t || !t.total) return;
  $("progresso-contagem").textContent = t.etapa === "video" ? `${tempoVideo(t.feitas)} de ${tempoVideo(t.total)}` : `${t.feitas} de ${t.total}`;
  $("progresso-barra").style.width = `${Math.min(100, (100 * t.feitas) / t.total)}%`;
}

function acompanhar(desde) {
  abrirPainel(estado.tarefa.etapa);
  const fonte = new EventSource(`/api/tarefas/eventos?desde=${desde}`);
  estado.tarefa.fonte = fonte;
  fonte.onmessage = (msg) => tratarEvento(JSON.parse(msg.data));
  fonte.onerror = () => {
    // O servidor fecha o stream ao terminar; se caiu antes do "fim", consulta o estado.
    if (fonte.readyState === EventSource.CLOSED && estado.tarefa) finalizar(false, "Conexão com o servidor perdida");
  };
}

function tratarEvento(e) {
  const t = estado.tarefa;
  if (!t) return;
  switch (e.tipo) {
    case "video_progresso":
      t.total = e.total || 0;
      t.feitas = e.segundos;
      t.pausado = e.situacao === "aguardando_cota";
      atualizarContagem();
      break;
    case "log":
      registrar(e.mensagem, "ok");
      break;
    case "troca":
      registrar(`${e.de} parou: ${e.motivo}`, "erro");
      registrar(`Seguindo com ${e.para}.`, "ok");
      break;
    case "capitulo_inicio":
      registrar(`${nomeCap(e.cap)}…`);
      break;
    case "fala": {
      t.feitas += 1;
      atualizarContagem();
      const seg = document.querySelector(`.faixa[data-cap="${e.cap}"] .faixa-fala[data-ordem="${e.ordem}"]`);
      if (seg) seg.className = e.ok ? "faixa-fala feita agora" : "faixa-fala falhou";
      if (!e.ok) registrar(`Fala ${e.ordem} (${e.personagem}): ${e.estado}`, "erro");
      break;
    }
    case "capitulo": {
      const resumo = `${nomeCap(e.cap)}: ${e.geradas} gerada(s), ${e.reusadas} do cache`;
      if (e.falhas.length) registrar(`${resumo}, ${e.falhas.length} falha(s). Áudio não montado.`, "erro");
      else registrar(e.montado ? `${resumo}. Áudio montado.` : `${nomeCap(e.cap)}: sem falas`, "ok");
      break;
    }
    case "erro":
      registrar(e.mensagem, "erro");
      break;
    case "fim":
      finalizar(e.ok);
      break;
  }
}

async function finalizar(ok, mensagem) {
  const t = estado.tarefa;
  t?.fonte?.close();
  estado.tarefa = null;
  const painel = $("progresso");
  const pausado = ok && t?.pausado;
  painel.dataset.fim = pausado ? "pausado" : ok ? "ok" : "erro";
  if (ok && !pausado) {
    $("progresso-barra").style.width = "100%";
    // Sucesso some sozinho; erro fica até ser lido e fechado.
    setTimeout(() => { if (!estado.tarefa && painel.dataset.fim === "ok") painel.hidden = true; }, 5000);
  }
  $("progresso-titulo").textContent = mensagem || (pausado ? "Pausado — trechos salvos" : ok ? "Pronto" : "Terminou com erro");
  $("progresso-fechar").hidden = false;
  if (mensagem) registrar(mensagem, "erro");
  estado.videos = null;
  await carregarLivros();
  if (estado.slug) await recarregarLivro();
  await carregarChaves();  // a síntese pode ter esbarrado em cota, crédito ou chave recusada
}

$("progresso-fechar").addEventListener("click", () => ($("progresso").hidden = true));

// ---------- início ----------

(async function iniciar() {
  try {
    await carregarLivros();
  } catch (e) {
    $("principal").replaceChildren(h("div", { class: "vazio" }, h("h2", {}, "O servidor não respondeu"), e.message));
    return;
  }
  await aoMudarHash();
  renderChaves();
  carregarChaves();  // confere online: não segura a abertura
  // Uma etapa pode estar rodando desde antes de a página abrir.
  const { rodando, proximo } = await api("/api/tarefas");
  if (rodando) {
    estado.tarefa = { etapa: rodando.etapa, livro: rodando.livro, total: 0, feitas: 0 };
    acompanhar(proximo);
    $("progresso-titulo").textContent = `${ROTULO_ETAPA[rodando.etapa]} (já estava rodando)`;
    render();
  }
})();
