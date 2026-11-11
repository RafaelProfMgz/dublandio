"""Estágio 3: manifesto -> um WAV por capítulo.

Cada fala é guardada em cache pelo hash de (provedor, voz, idioma, texto): rodar de
novo só sintetiza o que mudou. O capítulo só é montado se todas as falas existirem,
para nunca gerar um áudio com trechos faltando em silêncio.

Um erro com `interromper` (cota esgotada, chave inválida) passa a síntese para o
provedor reserva do livro, se houver; sem reserva, para tudo na hora. Na reserva,
cada fala usa a voz do personagem configurada para aquele provedor.
"""

import hashlib
import json
import time
import wave
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from dublandio import audio
from dublandio.config import Livro
from dublandio.roteiro import Fala, ler_manifesto
from dublandio.tts.base import ErroConfig, ErroTTS, Provedor


def chave_cache(provedor: str, voz: str, idioma: str, texto: str) -> str:
    return hashlib.sha256("\x1f".join((provedor, voz, idioma, texto)).encode()).hexdigest()[:16]


def voz_no_provedor(livro: Livro, fala: Fala, provedor: str) -> str | None:
    """Voz da fala no provedor: a do manifesto no principal; nos outros, a do livro.yaml."""
    if provedor == livro.provedor:
        return fala.voz
    try:
        return livro.voz(fala.personagem, provedor)
    except KeyError:
        return None


def parte_em_cache(livro: Livro, cap: str, fala: Fala) -> Path | None:
    """Áudio da fala já gerado por qualquer provedor do livro (o principal primeiro)."""
    for nome in livro.provedores:
        voz = voz_no_provedor(livro, fala, nome)
        if voz is not None:
            parte = livro.dir_cache / cap / f"{chave_cache(nome, voz, livro.idioma, fala.texto)}.wav"
            if parte.exists():
                return parte
    return None


class Cadeia:
    """Provedores em ordem de preferência. Quando o atual esgota, `trocar` passa ao próximo."""

    def __init__(self, provedores: Iterable[Provedor]):
        self._lista = list(provedores)
        self._i = 0

    @property
    def atual(self) -> Provedor:
        return self._lista[self._i]

    def trocar(self) -> bool:
        if self._i + 1 >= len(self._lista):
            return False
        self._i += 1
        return True


def cadeia_do_livro(livro: Livro, fabrica: Callable[[str], Provedor]) -> tuple[Cadeia, list[str]]:
    """Os provedores do livro que têm chave, na ordem dele, e avisos sobre os que ficaram de fora."""
    provedores, avisos = [], []
    for nome in livro.provedores:
        try:
            provedores.append(fabrica(nome))
        except ErroConfig as e:
            avisos.append(f"{nome} fora da síntese: {e}")
    if not provedores:
        raise ErroConfig("; ".join(avisos))
    return Cadeia(provedores), avisos


@dataclass
class Resultado:
    cap: str
    geradas: int = 0
    reusadas: int = 0
    falhas: list[tuple[Fala, str]] = field(default_factory=list)
    arquivo: Path | None = None


def _sintetizar_com_retentativas(provedor: Provedor, texto: str, voz: str, idioma: str, tentativas: int, espera: float) -> bytes:
    for i in range(tentativas):
        try:
            return provedor.sintetizar(texto, voz, idioma)
        except ErroTTS as e:
            if not e.retentavel or e.interromper or i == tentativas - 1:
                raise
            time.sleep(espera * 2**i)
    raise AssertionError("inalcançável")


def sintetizar_capitulo(
    livro: Livro,
    manifesto: Path,
    provedor: Provedor | Cadeia,
    tentativas: int = 3,
    espera: float = 1.0,
    juntar: Callable[[list[Path], Path], None] = audio.concatenar,
    ao_progredir: Callable[[Fala, str], None] | None = None,
    ao_trocar: Callable[[str, str, str], None] | None = None,
) -> Resultado:
    """`ao_trocar(de, para, motivo)` avisa quando a síntese muda para o provedor reserva."""
    cadeia = provedor if isinstance(provedor, Cadeia) else Cadeia([provedor])
    cap = manifesto.stem
    resultado = Resultado(cap)
    pasta_cache = livro.dir_cache / cap
    pasta_cache.mkdir(parents=True, exist_ok=True)

    partes: list[Path] = []
    quem: list[str] = []  # personagem de cada parte, para o mapa de falas do vídeo
    for fala in ler_manifesto(manifesto):
        if (existente := parte_em_cache(livro, cap, fala)) is not None:
            partes.append(existente)
            quem.append(fala.personagem)
            resultado.reusadas += 1
            continue
        while True:  # repete a mesma fala só quando troca de provedor
            atual = cadeia.atual
            voz = voz_no_provedor(livro, fala, atual.nome)
            try:
                if voz is None:
                    raise ErroTTS(f"o livro não define voz de {fala.personagem} nem do Narrador para o {atual.nome}",
                                  interromper=True)
                wav = _sintetizar_com_retentativas(atual, fala.texto, voz, livro.idioma, tentativas, espera)
            except ErroTTS as e:
                if e.interromper and cadeia.trocar():
                    if ao_trocar:
                        ao_trocar(atual.nome, cadeia.atual.nome, str(e))
                    continue
                if ao_progredir:
                    ao_progredir(fala, f"falhou: {e}")
                if e.interromper:  # sem reserva, nenhuma fala seguinte passaria: não adianta continuar
                    raise
                resultado.falhas.append((fala, str(e)))
                break
            parte = pasta_cache / f"{chave_cache(atual.nome, voz, livro.idioma, fala.texto)}.wav"
            parte.write_bytes(wav)
            partes.append(parte)
            quem.append(fala.personagem)
            resultado.geradas += 1
            if ao_progredir:
                ao_progredir(fala, "ok")
            break

    if partes and not resultado.falhas:
        destino = livro.dir_audio / f"{cap}.wav"
        juntar(partes, destino)
        gravar_mapa_de_falas(destino, list(zip(quem, partes, strict=True)))
        resultado.arquivo = destino
    return resultado


def arquivo_mapa_de_falas(wav: Path) -> Path:
    return wav.with_suffix(".falas.json")


def gravar_mapa_de_falas(wav: Path, falas: list[tuple[str, Path]]) -> Path | None:
    """Grava ao lado do WAV do capítulo quem fala em cada trecho (em amostras do WAV final).

    O vídeo usa este mapa para trocar o avatar a cada personagem, sem depender do .cache.
    Sem como ler o WAV ou as partes (ex.: formato inesperado), não grava nada.
    """
    destino = arquivo_mapa_de_falas(wav)
    destino.unlink(missing_ok=True)  # um mapa velho nunca pode valer para um áudio novo
    try:
        with wave.open(str(wav)) as w:
            total, taxa = w.getnframes(), w.getframerate()
        segmentos, inicio = [], 0
        for personagem, parte in falas:
            with wave.open(str(parte)) as w:
                # Partes em outra taxa são convertidas na montagem do capítulo.
                quadros = round(w.getnframes() * taxa / w.getframerate())
            segmentos.append([personagem, inicio, quadros])
            inicio += quadros
    except (wave.Error, EOFError, OSError):
        return None
    if not segmentos or abs(inicio - total) > taxa // 10:
        return None
    segmentos[-1][2] += total - inicio  # absorve o arredondamento das conversões
    destino.write_text(json.dumps({"total": total, "taxa": taxa, "segmentos": segmentos}, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    return destino


def ler_mapa_de_falas(wav: Path) -> list[tuple[str, int, int]] | None:
    """O mapa gravado na síntese, se ainda corresponder ao WAV (mesmo tamanho e taxa)."""
    path = arquivo_mapa_de_falas(wav)
    try:
        dados = json.loads(path.read_text(encoding="utf-8"))
        with wave.open(str(wav)) as w:
            if (w.getnframes(), w.getframerate()) != (dados["total"], dados["taxa"]):
                return None
        return [(str(p), int(i), int(q)) for p, i, q in dados["segmentos"]]
    except (OSError, ValueError, KeyError, TypeError, wave.Error, EOFError):
        return None


def sintetizar_livro(livro: Livro, provedor: Provedor | Cadeia, caps: list[int] | None = None, **opcoes) -> list[Resultado]:
    manifestos = sorted(livro.dir_manifesto.glob("cap_*.json"))
    if caps:
        quero = {f"cap_{n:03d}" for n in caps}
        manifestos = [m for m in manifestos if m.stem in quero]
    cadeia = provedor if isinstance(provedor, Cadeia) else Cadeia([provedor])  # a troca vale para os capítulos seguintes
    return [sintetizar_capitulo(livro, m, cadeia, **opcoes) for m in manifestos]
