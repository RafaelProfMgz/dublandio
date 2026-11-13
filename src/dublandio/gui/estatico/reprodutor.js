// Um áudio e uma fila independentes da página aberta. A barra permanece ao navegar.
class ReprodutorAudio {
  constructor(audio, raiz, { aoMudar = () => {}, aoFalhar = () => {} } = {}) {
    this.audio = audio;
    this.raiz = raiz;
    this.aoMudar = aoMudar;
    this.aoFalhar = aoFalhar;
    this.fila = [];
    this.indice = -1;
    this.versao = 0;
    this.carregando = false;
    this.el = Object.fromEntries([...raiz.querySelectorAll('[data-player]')].map((el) => [el.dataset.player, el]));
    this.el.play.addEventListener('click', () => this.alternarAtual());
    this.el.anterior.addEventListener('click', () => this.mover(-1));
    this.el.proximo.addEventListener('click', () => this.mover(1));
    this.el.posicao.addEventListener('input', () => {
      const duracao = this.duracao();
      if (duracao) audio.currentTime = Math.max(0, Math.min(duracao, Number(this.el.posicao.value) || 0));
      this.atualizar();
    });
    this.el.volume.addEventListener('input', () => {
      const volume = Math.max(0, Math.min(1, Number(this.el.volume.value) / 100));
      audio.muted = false;
      audio.volume = volume;
    });
    this.el.mudo.addEventListener('click', () => {
      if (!audio.volume) { audio.volume = 0.5; audio.muted = false; }
      else audio.muted = !audio.muted;
    });
    try {
      const salvo = localStorage.getItem('dublandio-volume');
      if (salvo !== null && Number.isFinite(Number(salvo))) audio.volume = Math.max(0, Math.min(1, Number(salvo)));
    } catch { /* O player funciona sem armazenamento local. */ }
    audio.addEventListener('volumechange', () => {
      try { localStorage.setItem('dublandio-volume', String(audio.volume)); } catch { /* Sem armazenamento. */ }
      this.atualizar();
    });
    for (const evento of ['play', 'pause', 'timeupdate', 'loadedmetadata', 'durationchange', 'emptied']) {
      audio.addEventListener(evento, () => this.atualizar());
    }
    audio.addEventListener('waiting', () => { this.carregando = true; this.atualizar(); });
    audio.addEventListener('playing', () => { this.carregando = false; this.atualizar(); });
    audio.addEventListener('error', () => {
      this.versao++;
      audio.pause();
      this.carregando = false;
      this.atualizar();
      this.aoFalhar('Não foi possível carregar este áudio. Tente reproduzir novamente.');
    });
    audio.addEventListener('ended', () => {
      if (this.indice + 1 < this.fila.length) this.mover(1);
      else this.atualizar();
    });
    this.atualizar();
  }

  get atual() { return this.fila[this.indice] || null; }
  duracao() { return Number.isFinite(this.audio.duration) && this.audio.duration > 0 ? this.audio.duration : 0; }

  static tempo(segundos) {
    const valor = Math.floor(Number.isFinite(segundos) && segundos > 0 ? segundos : 0);
    const s = String(valor % 60).padStart(2, '0');
    const m = Math.floor(valor / 60) % 60;
    const horas = Math.floor(valor / 3600);
    return horas ? `${horas}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
  }

  alternar(item, fila = [item]) {
    if (this.atual?.chave === item.chave && this.atual.url === item.url) {
      this.alternarAtual();
      return;
    }
    const unicos = new Map(fila.filter((f) => f.url).map((f) => [f.chave, { ...f }]));
    if (!unicos.has(item.chave)) this.fila = [{ ...item }, ...unicos.values()];
    else this.fila = [...unicos.values()];
    this.indice = this.fila.findIndex((f) => f.chave === item.chave);
    this.iniciar();
  }

  async reproduzir() {
    const versao = ++this.versao;
    try {
      if (this.audio.error) this.audio.load();
      if (this.audio.ended) this.audio.currentTime = 0;
      await this.audio.play();
    } catch (e) {
      if (versao !== this.versao) return; // Uma troca de faixa pode cancelar o play anterior.
      this.carregando = false;
      this.aoFalhar(`Não deu para tocar: ${e.message}`);
    }
    if (versao === this.versao) this.atualizar();
  }

  alternarAtual() {
    if (!this.atual) return;
    if (this.audio.paused || this.audio.ended) this.reproduzir();
    else {
      this.versao++;
      this.audio.pause();
      this.carregando = false;
      this.atualizar();
    }
  }

  iniciar() {
    if (!this.atual) return;
    this.audio.src = this.atual.url;
    this.carregando = true;
    this.atualizar();
    this.reproduzir();
  }

  mover(direcao) {
    const indice = this.indice + direcao;
    if (indice < 0 || indice >= this.fila.length) return;
    this.indice = indice;
    this.iniciar();
  }

  acoplarModal(modal) {
    // Elementos fora de um dialog modal ficam inertes: mantém os controles acessíveis.
    modal.append(this.raiz);
    modal.classList.add('com-reprodutor');
    modal.addEventListener('close', () => document.body.append(this.raiz), { once: true });
  }

  atualizar() {
    const item = this.atual;
    const tocando = !!item && !this.audio.paused && !this.audio.ended;
    this.raiz.hidden = !item;
    document.body.classList.toggle('player-visivel', !!item);
    this.el.titulo.textContent = item?.titulo || '';
    this.el.subtitulo.textContent = item?.subtitulo || '';
    this.el.titulo.title = item?.titulo || '';
    this.el.subtitulo.title = item?.subtitulo || '';
    const situacao = this.carregando ? 'Carregando áudio' : tocando ? 'Reproduzindo' : this.audio.ended ? 'Concluído' : 'Pausado';
    if (this.el.estado.textContent !== situacao) this.el.estado.textContent = situacao;
    this.el.play.setAttribute('aria-label', tocando ? 'Pausar áudio' : 'Reproduzir áudio');
    this.el.play.setAttribute('title', tocando ? 'Pausar' : 'Reproduzir');
    this.el.play.setAttribute('aria-pressed', String(tocando));
    this.el.icone.setAttribute('href', tocando ? '#i-pause' : '#i-play');
    this.el.anterior.disabled = this.indice <= 0;
    this.el.proximo.disabled = this.indice < 0 || this.indice + 1 >= this.fila.length;
    this.el.anterior.title = this.indice > 0 ? `Anterior: ${this.fila[this.indice - 1].titulo}` : 'Não há áudio anterior';
    this.el.proximo.title = this.indice + 1 < this.fila.length ? `Próximo: ${this.fila[this.indice + 1].titulo}` : 'Não há próximo áudio';
    const duracao = this.duracao();
    const posicao = Math.max(0, Math.min(duracao, this.audio.currentTime || 0));
    this.el.posicao.disabled = !duracao;
    this.el.posicao.max = String(duracao || 1);
    this.el.posicao.value = String(posicao);
    this.el.posicao.setAttribute('aria-valuetext', `${ReprodutorAudio.tempo(posicao)} de ${ReprodutorAudio.tempo(duracao)}`);
    this.el.posicao.style.setProperty('--preenchido', `${duracao ? posicao / duracao * 100 : 0}%`);
    this.el.decorrido.textContent = ReprodutorAudio.tempo(posicao);
    this.el.duracao.textContent = duracao ? ReprodutorAudio.tempo(duracao) : '--:--';
    const volume = this.audio.muted ? 0 : Math.round(this.audio.volume * 100);
    this.el.volume.value = String(volume);
    this.el.volume.setAttribute('aria-valuetext', `${volume}%`);
    this.el.volume.style.setProperty('--preenchido', `${volume}%`);
    this.el.mudo.setAttribute('aria-label', volume ? 'Silenciar áudio' : 'Ativar som');
    this.el.mudo.setAttribute('aria-pressed', String(!volume));
    this.el.volumeIcone.setAttribute('href', volume ? '#i-volume' : '#i-mudo');
    this.aoMudar(item, tocando);
  }
}
