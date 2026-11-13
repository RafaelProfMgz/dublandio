// Testes de estado e eventos com áudio/DOM simulados, sem rede nem síntese.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Elemento extends EventTarget {
  constructor(nome) {
    super(); this.dataset = { player: nome }; this.attrs = {}; this.children = [];
    this.style = { setProperty: (k, v) => { this.attrs[k] = v; } };
    this.classes = new Set();
    this.classList = { add: (k) => this.classes.add(k), toggle: (k, on) => on ? this.classes.add(k) : this.classes.delete(k) };
  }
  setAttribute(k, v) { this.attrs[k] = v; }
  append(el) {
    if (el.parent) el.parent.children = el.parent.children.filter((c) => c !== el);
    el.parent = this; this.children.push(el);
  }
  emitir(evento) { this.dispatchEvent(new Event(evento)); }
}
class AudioSimulado extends EventTarget {
  constructor() { super(); this.paused = true; this.ended = false; this.currentTime = 0; this.duration = NaN; this._volume = 1; this._muted = false; this.fontes = 0; this.loads = 0; }
  emitir(evento) { this.dispatchEvent(new Event(evento)); }
  set src(v) { this._src = v; this.fontes++; this.currentTime = 0; this.duration = NaN; this.ended = false; this.error = null; this.paused = true; this.emitir('emptied'); }
  get src() { return this._src; }
  set volume(v) { this._volume = v; this.emitir('volumechange'); }
  get volume() { return this._volume; }
  set muted(v) { this._muted = v; this.emitir('volumechange'); }
  get muted() { return this._muted; }
  pause() { this.paused = true; this.emitir('pause'); }
  load() { this.loads++; this.error = null; this.currentTime = 0; }
  play() {
    if (this.falharPlay) { this.paused = true; return Promise.reject(new Error('bloqueado')); }
    this.paused = false; this.ended = false; this.emitir('play'); this.emitir('playing');
    return this.playPendente || Promise.resolve();
  }
}
const body = new Elemento('body');
const cache = new Map([['dublandio-volume', '.3']]);
const contexto = { document: { body }, localStorage: { getItem: (k) => cache.get(k) ?? null, setItem: (k, v) => cache.set(k, v) } };
vm.createContext(contexto);
vm.runInContext(fs.readFileSync('src/dublandio/gui/estatico/reprodutor.js', 'utf8') + '\nglobalThis.ReprodutorAudio = ReprodutorAudio;', contexto);
const Player = contexto.ReprodutorAudio;
const raiz = new Elemento('raiz');
const campos = Object.fromEntries(['play', 'anterior', 'proximo', 'posicao', 'volume', 'mudo', 'titulo', 'subtitulo', 'estado', 'icone', 'decorrido', 'duracao', 'volumeIcone'].map((k) => [k, new Elemento(k)]));
raiz.querySelectorAll = () => Object.values(campos);
const audio = new AudioSimulado();
const erros = [];
let ultimaMudanca;
const p = new Player(audio, raiz, { aoMudar: (item, tocando) => ultimaMudanca = { item, tocando }, aoFalhar: (e) => erros.push(e) });
const fila = [1, 2, 3].map((n) => ({ chave: `livro-a:${n}`, url: `/a/${n}.wav`, titulo: `Capítulo ${n}`, subtitulo: 'Livro A' }));
const esperar = () => new Promise(setImmediate);

(async () => {
  assert.equal(raiz.hidden, true);
  assert.equal(audio.volume, .3);
  p.alternar(fila[0], fila);
  await esperar();
  assert.equal(raiz.hidden, false);
  assert.equal(campos.titulo.textContent, 'Capítulo 1');
  assert.equal(campos.subtitulo.textContent, 'Livro A');
  assert.equal(campos.anterior.disabled, true);
  assert.equal(campos.proximo.disabled, false);
  assert.equal(campos.posicao.disabled, true, 'Duração desconhecida desativa avanço');
  assert.equal(ultimaMudanca.tocando, true);

  audio.duration = 180; audio.currentTime = 42; audio.emitir('loadedmetadata');
  assert.equal(campos.decorrido.textContent, '0:42');
  assert.equal(campos.duracao.textContent, '3:00');
  assert.equal(campos.posicao.attrs['aria-valuetext'], '0:42 de 3:00');
  campos.play.emitir('click');
  assert.equal(audio.paused, true);
  assert.equal(raiz.hidden, false, 'Barra permanece visível ao pausar');
  p.alternar(fila[0], fila); await esperar();
  assert.equal(audio.currentTime, 42, 'Retomar não reinicia o áudio');
  assert.equal(audio.fontes, 1);
  campos.posicao.value = '90'; campos.posicao.emitir('input');
  assert.equal(audio.currentTime, 90);
  assert.equal(campos.decorrido.textContent, '1:30');
  campos.posicao.value = '999'; campos.posicao.emitir('input');
  assert.equal(audio.currentTime, 180, 'Avanço respeita o fim do arquivo');

  campos.volume.value = '64'; campos.volume.emitir('input');
  assert.equal(audio.volume, .64);
  assert.equal(cache.get('dublandio-volume'), '0.64');
  campos.mudo.emitir('click');
  assert.equal(audio.muted, true);
  assert.equal(campos.volume.value, '0');
  campos.mudo.emitir('click');
  assert.equal(audio.muted, false);
  assert.equal(campos.volume.value, '64');
  campos.volume.value = '0'; campos.volume.emitir('input');
  campos.mudo.emitir('click');
  assert.equal(audio.volume, .5);

  campos.proximo.emitir('click'); await esperar();
  assert.equal(p.atual.chave, 'livro-a:2');
  assert.equal(campos.anterior.disabled, false);
  campos.anterior.emitir('click'); await esperar();
  assert.equal(p.atual.chave, 'livro-a:1');
  audio.ended = true; audio.paused = true; audio.emitir('ended'); await esperar();
  assert.equal(p.atual.chave, 'livro-a:2', 'Fim avança para o próximo áudio disponível');
  p.mover(1); await esperar();
  assert.equal(campos.proximo.disabled, true);
  audio.ended = true; audio.paused = true; audio.emitir('ended');
  assert.equal(ultimaMudanca.tocando, false);
  assert.equal(p.atual.chave, 'livro-a:3');
  campos.play.emitir('click'); await esperar();
  assert.equal(audio.currentTime, 0, 'Reproduzir após o fim reinicia a última faixa');

  const outra = { chave: 'livro-b:1', url: '/b/1.wav', titulo: 'Capítulo 1', subtitulo: 'Livro B' };
  p.alternar(outra); await esperar();
  assert.equal(audio.src, '/b/1.wav', 'Capítulos com mesmo número de livros diferentes não se confundem');
  assert.equal(campos.proximo.disabled, true);
  assert.equal(campos.anterior.disabled, true);
  audio.error = { code: 4 }; audio.emitir('error');
  assert.equal(ultimaMudanca.tocando, false);
  assert.equal(erros.length, 1);
  campos.play.emitir('click'); await esperar();
  assert.equal(audio.loads, 1, 'Permite recarregar após falha');
  audio.pause(); audio.falharPlay = true;
  campos.play.emitir('click'); await esperar();
  assert.equal(erros.length, 2);
  assert.equal(ultimaMudanca.tocando, false);
  audio.falharPlay = false;

  let rejeitar;
  audio.playPendente = new Promise((_, reject) => { rejeitar = reject; });
  p.alternar(fila[0], fila);
  audio.playPendente = null;
  p.mover(1); await esperar();
  rejeitar(new Error('play anterior interrompido')); await esperar();
  assert.equal(erros.length, 2, 'Rejeição de faixa antiga não interfere na nova');
  assert.equal(p.atual.chave, 'livro-a:2');
  assert.equal(ultimaMudanca.tocando, true);

  const modal = new Elemento('dialog');
  p.acoplarModal(modal);
  assert.equal(raiz.parent, modal);
  modal.emitir('close');
  assert.equal(raiz.parent, body, 'Controles voltam ao rodapé quando o dialog fecha');
  assert.equal(Player.tempo(3661), '1:01:01');
  assert.equal(Player.tempo(NaN), '0:00');

  // Integração com os botões reais da tela: ignora capítulos sem áudio e captura o livro.
  const chamadas = [];
  contexto.estado = { slug: 'a', livro: { titulo: 'Livro A', lista: [
    { cap: 'cap_001', tem_audio: true, audio_versao: 1 },
    { cap: 'cap_002', tem_audio: false },
    { cap: 'cap_003', tem_audio: true, audio_versao: 2 },
  ] } };
  contexto.reprodutor = { alternar: (item, fila) => chamadas.push({ item, fila }) };
  contexto.h = (tag, attrs) => Object.assign(new Elemento(tag), attrs);
  contexto.document.createElementNS = () => new Elemento('svg');
  contexto.rotuloIdioma = (i) => i;
  contexto.nomeCap = (cap) => `Capítulo ${Number(cap.slice(4))}`;
  const app = fs.readFileSync('src/dublandio/gui/estatico/app.js', 'utf8');
  vm.runInContext(app.slice(app.indexOf('// Um player só'), app.indexOf('function telaCapitulos')), contexto);
  const botao = contexto.botaoTocarCapitulo(contexto.estado.livro.lista[0]);
  contexto.estado.slug = 'b';
  botao.onclick();
  assert.deepEqual(Array.from(chamadas[0].fila, (f) => f.chave), ['cap:a:cap_001', 'cap:a:cap_003']);
  assert.equal(chamadas[0].item.subtitulo, 'Livro A');
  assert.equal(chamadas[0].item.url, '/api/livros/a/audio/cap_001?v=1');
  console.log('Player: pausa/retomada, progresso, volume, fila, fim, erros, troca rápida e dialog conferidos.');
})().catch((erro) => { console.error(erro); process.exitCode = 1; });
