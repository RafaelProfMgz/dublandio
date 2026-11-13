// Regressões do seletor com DOM simulado; não substituem inspeção visual no navegador.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Elemento {
  constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.events = {}; this.dataset = {}; this.value = ''; this.style = { setProperty() {} }; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  setAttribute(k, v) {
    this.attrs[k] = v;
    if (k === 'value') this.value = v;
    if (k === 'disabled' || k === 'hidden') this[k] = true;
    if (k === 'data-personagem-voz') this.dataset.personagemVoz = v;
  }
  addEventListener(k, f) { (this.events[k] ||= []).push(f); }
  async emitir(k) { for (const f of this.events[k] || []) await f({ target: this, preventDefault() {} }); }
  querySelectorAll(selector) { return descendentes(this).filter((el) => selector === 'button' ? el.tag === 'button' : selector === '[data-personagem-voz]' ? !!el.dataset.personagemVoz : false); }
  showModal() { this.open = true; }
  close() { this.open = false; this.emitir('close'); }
  focus() { this.focado = true; }
  remove() { this.removido = true; }
  get textContent() { return this.children.map((c) => c instanceof Elemento ? c.textContent : c).join(''); }
  set textContent(t) { this.children = [t]; }
}
function descendentes(el) { return el.children.filter((c) => c instanceof Elemento).flatMap((c) => [c, ...descendentes(c)]); }

const vozes = [
  { id: 'n', nome: 'Narrador', genero: 'male', idioma: 'Portuguese' },
  { id: 'a', nome: 'Ana', genero: 'female', idioma: 'Portuguese', idade: 'Adulta', sotaque: 'Brasileiro', descricao: 'Narração acolhedora' },
  { id: 'b', nome: 'Educated British Baritone', genero: 'male', idioma: 'English' },
  { id: 'x', nome: 'Sem dados', genero: '', idioma: '' },
];
const body = new Elemento('body');
const livro = { provedor: 'heygen', idioma_catalogo: 'Portuguese', mapa_vozes: { Narrador: 'n' } };
const pedidos = [];
let falhar = false;
let renders = 0;
const contexto = {
  Node: Elemento,
  document: { body, createElement: (tag) => new Elemento(tag), querySelectorAll: (s) => body.querySelectorAll(s) },
  estado: { slug: 'ex', livro, catalogo: { heygen: { vozes } }, sujo: false },
  NARRADOR: 'Narrador', plural: (n, um, varios) => `${n} ${n === 1 ? um : varios}`,
  carregarCatalogo: async () => ({ vozes }),
  api: async (url, opcoes) => {
    pedidos.push({ url, opcoes });
    if (falhar) throw new Error('Falha de gravação');
    return opcoes ? {} : { ...livro, mapa_vozes: { Narrador: 'n', Ana: 'a' } };
  },
  render: () => renders++, avisar() {}, marcarTocando() {}, player: { pause() {} },
  reprodutor: { acoplarModal() {} },
};
const codigo = fs.readFileSync('src/dublandio/gui/estatico/app.js', 'utf8');
vm.createContext(contexto);
vm.runInContext(codigo.slice(codigo.indexOf('function h('), codigo.indexOf('const SVG =')), contexto);
vm.runInContext(codigo.slice(codigo.indexOf('const NOMES_IDIOMA'), codigo.indexOf('function telaCatalogo')), contexto);
const encontrar = (root, pred) => descendentes(root).find(pred);
const lista = (modal) => encontrar(modal, (el) => el.attrs['aria-label'] === 'Vozes disponíveis');
const campo = (modal, label) => encontrar(modal, (el) => el.attrs['aria-label'] === label);
const esperar = () => new Promise(setImmediate);

(async () => {
  assert.equal(contexto.sotaqueDaVoz(vozes[0]), '', 'Português não implica sotaque brasileiro');
  assert.equal(contexto.sotaqueDaVoz(vozes[2]), 'Britânico');
  contexto.abrirSeletorVoz(livro, 'Ana', new Elemento('button'));
  await esperar();
  let modal = body.children.at(-1);
  assert.equal(modal.open, true);
  assert.match(lista(modal).textContent, /Idade: Adulta/);
  assert.match(lista(modal).textContent, /Sotaque: Britânico \(no nome\)/);
  assert.match(lista(modal).textContent, /Idade: não informada/);

  const genero = campo(modal, 'Filtrar gênero');
  genero.value = 'female'; await genero.emitir('change');
  assert.match(lista(modal).textContent, /Ana/);
  assert.doesNotMatch(lista(modal).textContent, /Baritone/);
  const busca = campo(modal, 'Buscar voz');
  busca.value = 'narracao acolhedora'; await busca.emitir('input');
  assert.match(lista(modal).textContent, /Ana/, 'Busca ignora acentos e inclui descrição');
  busca.value = 'inexistente'; await busca.emitir('input');
  assert.match(lista(modal).textContent, /Nenhuma voz encontrada/);
  busca.value = ''; await busca.emitir('input');
  genero.value = ''; await genero.emitir('change');
  const sotaque = campo(modal, 'Filtrar sotaque');
  sotaque.value = 'Britânico'; await sotaque.emitir('change');
  assert.match(lista(modal).textContent, /Baritone/);
  assert.doesNotMatch(lista(modal).textContent, /Narração acolhedora/);
  sotaque.value = '?'; await sotaque.emitir('change');
  assert.match(lista(modal).textContent, /Sem dados/);
  assert.doesNotMatch(lista(modal).textContent, /Baritone/);
  sotaque.value = ''; await sotaque.emitir('change');
  await campo(modal, 'Selecionar Ana para Ana').emitir('click');
  assert.equal(modal.open, false);
  assert.equal(renders, 1);
  assert.deepEqual(JSON.parse(pedidos[0].opcoes.body), { personagem: 'Ana', voz: 'a', provedor: 'heygen' });
  assert.equal(contexto.estado.livro.mapa_vozes.Ana, 'a');

  falhar = true;
  contexto.abrirSeletorVoz(livro, 'Ana', new Elemento('button'));
  await esperar();
  modal = body.children.at(-1);
  await campo(modal, 'Selecionar Ana para Ana').emitir('click');
  assert.equal(modal.open, true, 'Erro mantém o seletor aberto');
  assert.match(encontrar(modal, (el) => el.attrs.role === 'alert').textContent, /Falha de gravação/);
  assert.equal(campo(modal, 'Selecionar Ana para Ana').disabled, undefined, 'Permite tentar novamente');
  modal.close();
  console.log('Seletor: busca, filtros, metadados ausentes, gravação e recuperação de erro conferidos.');
})().catch((erro) => { console.error(erro); process.exitCode = 1; });
