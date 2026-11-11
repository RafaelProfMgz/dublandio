"""Áudio já aprovado -> clipes HeyGen -> MP4 por capítulo, com retomada local."""

import hashlib
import io
import json
import math
import shutil
import subprocess
import tempfile
import time
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

from dublandio import audio
from dublandio.config import Livro
from dublandio.roteiro import parse_roteiro
from dublandio.sintetizar import parte_em_cache

URL = "https://api.heygen.com/v3"
TAMANHOS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}


class ErroVideo(Exception):
    """Geração interrompida; os clipes e IDs já recebidos continuam salvos."""


@dataclass
class Trecho:
    cap: str
    ordem: int
    personagem: str
    avatar: str
    audio: str
    inicio: int  # amostras, para cortar sem perder nem repetir áudio
    quadros: int
    taxa: int
    chave: str

    @property
    def duracao(self):
        return self.quadros / self.taxa


def _hash(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def opcoes(livro: Livro) -> tuple[float, str, str]:
    segundos = livro.video.get("segundos_por_trecho", 30)
    if isinstance(segundos, bool) or not isinstance(segundos, (int, float)) or not math.isfinite(segundos) or not 1 <= segundos <= 120:
        raise ValueError("video.segundos_por_trecho deve estar entre 1 e 120")
    formato = livro.video.get("formato", "16:9")
    if formato not in TAMANHOS:
        raise ValueError("video.formato deve ser 16:9, 9:16 ou 1:1")
    motor = livro.video.get("motor", "avatar_iv")
    if motor not in ("avatar_iii", "avatar_iv", "avatar_v", "heygen-avatar-6"):
        raise ValueError("video.motor inválido")
    return segundos, formato, motor


def planejar(livro: Livro, caps: list[int] | None = None) -> list[Trecho]:
    """Não acessa a rede. Exige cache de todas as falas antes de gerar qualquer vídeo."""
    segundos, formato, motor = opcoes(livro)
    roteiros = sorted(livro.dir_roteiro.glob("cap_*.txt"))
    if caps:
        quero = {f"cap_{n:03d}" for n in caps}
        encontrados = {r.stem for r in roteiros}
        if faltam := quero - encontrados:
            raise ValueError(f"roteiro não encontrado: {', '.join(sorted(faltam))}")
        roteiros = [r for r in roteiros if r.stem in quero]
    if not roteiros:
        raise ValueError("nenhum roteiro encontrado")
    trechos = []
    for roteiro in roteiros:
        for fala in parse_roteiro(roteiro.read_text(encoding="utf-8"), livro):
            audio = parte_em_cache(livro, roteiro.stem, fala)
            if audio is None:
                raise ValueError(f"{roteiro.stem}, fala {fala.ordem} ({fala.personagem}): áudio não encontrado no cache; gere o áudio antes")
            avatar = livro.avatares.get(fala.personagem, "")
            if not isinstance(avatar, str):
                raise ValueError(f"ID de avatar inválido para {fala.personagem}")
            try:
                with wave.open(str(audio), "rb") as wav:
                    taxa, total = wav.getframerate(), wav.getnframes()
                    tamanho = wav.getnchannels() * wav.getsampwidth()
                    # A API de vídeo aceita áudios até 32 MB. Deixa margem para o cabeçalho.
                    passo = min(int(segundos * taxa), 31_000_000 // tamanho)
                    if not total:
                        raise ValueError(f"áudio vazio: {audio}")
                    if tamanho * total != len(wav.readframes(total)):
                        raise ValueError(f"WAV truncado: {audio}")
            except (wave.Error, EOFError) as e:
                raise ValueError(f"WAV PCM ilegível: {audio}: {e}") from e
            digest = _hash(audio.read_bytes())
            for inicio in range(0, total, passo):
                quadros = min(passo, total - inicio)
                chave = _hash(json.dumps([digest, inicio, quadros, avatar, formato, motor, "v1"]).encode())
                trechos.append(Trecho(roteiro.stem, fala.ordem, fala.personagem, avatar,
                                     str(audio.resolve()), inicio, quadros, taxa, chave))
    if not trechos:
        raise ValueError("roteiros sem falas")
    return trechos


def _gravar(path: Path, dados) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporario = path.with_suffix(".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporario.replace(path)


def salvar_plano(livro: Livro, trechos: list[Trecho]) -> Path:
    destino = livro.dir / "video" / "plano.json"
    _gravar(destino, {"opcoes": livro.video, "trechos": [asdict(t) for t in trechos]})
    return destino


def recortar(trecho: Trecho) -> bytes:
    """Copia as amostras originais, sem sintetizar nem recodificar a fala."""
    saida = io.BytesIO()
    with wave.open(trecho.audio, "rb") as origem:
        origem.setpos(trecho.inicio)
        with wave.open(saida, "wb") as destino:
            destino.setparams(origem.getparams())
            destino.writeframes(origem.readframes(trecho.quadros))
    return saida.getvalue()


class HeyGenVideo:
    def __init__(self, chave: str):
        self.headers = {"X-Api-Key": chave}

    def _requisitar(self, metodo: str, rota: str, **kwargs) -> dict:
        try:
            r = requests.request(metodo, f"{URL}/{rota}", headers=self.headers, timeout=120, **kwargs)
        except requests.RequestException as e:
            raise ErroVideo("HeyGen indisponível; rode novamente para retomar") from e
        if not 200 <= r.status_code < 300:
            raise ErroVideo(f"HeyGen HTTP {r.status_code}: {r.text[:500]}")
        try:
            return r.json()["data"]
        except (ValueError, KeyError, TypeError) as e:
            raise ErroVideo("resposta HeyGen sem data") from e

    def enviar_audio(self, dados: bytes) -> str:
        resposta = self._requisitar("POST", "assets", files={"file": ("fala.wav", dados, "audio/wav")})
        if not resposta.get("asset_id"):
            raise ErroVideo("upload sem asset_id")
        return resposta["asset_id"]

    def criar(self, payload: dict, chave: str) -> str:
        # A chave é persistida ANTES da chamada. Timeout de POST não dispara geração às cegas.
        headers = {**self.headers, "Idempotency-Key": chave}
        anteriores = self.headers
        self.headers = headers
        try:
            resposta = self._requisitar("POST", "videos", json=payload)
        finally:
            self.headers = anteriores
        if not resposta.get("video_id"):
            raise ErroVideo("geração sem video_id; mantenha o estado para retomar")
        return resposta["video_id"]

    def baixar(self, video_id: str, destino: Path, consultas: int = 120, intervalo: float = 10) -> None:
        for i in range(consultas):
            dados = self._requisitar("GET", f"videos/{video_id}")
            if dados.get("status") == "failed":
                raise ErroVideo(f"vídeo {video_id} falhou: {dados.get('failure_message') or dados.get('failure_code')}; ID preservado para revisão")
            if dados.get("status") == "completed":
                if not dados.get("video_url"):
                    raise ErroVideo(f"vídeo {video_id} sem URL de download")
                temporario = destino.with_suffix(".download")
                try:
                    with requests.get(dados["video_url"], timeout=120, stream=True) as r:
                        r.raise_for_status()
                        with temporario.open("wb") as arquivo:
                            for bloco in r.iter_content(1024 * 1024):
                                arquivo.write(bloco)
                    if not temporario.stat().st_size:
                        raise ErroVideo("download vazio")
                    temporario.replace(destino)
                    return
                except requests.RequestException as e:
                    raise ErroVideo("falha ao baixar vídeo; rode novamente para retomar pelo ID salvo") from e
            if i + 1 < consultas:
                time.sleep(intervalo)
        raise ErroVideo(f"vídeo {video_id} ainda processando; rode novamente para retomar sem criar outro")


def juntar(trechos: list[Trecho], partes: list[Path], destino: Path, formato: str) -> None:
    """Normaliza imagem e usa a gravação original como trilha de cada clipe."""
    largura, altura = TAMANHOS[formato]
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destino.parent) as pasta:
        pasta = Path(pasta)
        ondas = []
        duracao_acumulada = 0.0
        frames_anteriores = 0
        for i, (trecho, video) in enumerate(zip(trechos, partes, strict=True)):
            wav = pasta / f"{i}.wav"
            wav.write_bytes(recortar(trecho))
            ondas.append(wav)
            duracao_acumulada += trecho.duracao
            frames_totais = round(duracao_acumulada * 30)
            frames = frames_totais - frames_anteriores
            frames_anteriores = frames_totais
            filtro = (f"scale={largura}:{altura}:force_original_aspect_ratio=decrease,"
                      f"pad={largura}:{altura}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,"
                      f"tpad=stop_mode=clone:stop_duration={trecho.duracao}")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
                            "-map", "0:v:0", "-an", "-vf", filtro,
                            "-frames:v", str(frames), "-c:v", "libx264", "-preset", "fast",
                            "-pix_fmt", "yuv420p",
                            str(pasta / f"{i}.mp4")], check=True)
        # Uma única codificação da trilha evita pausas artificiais de AAC entre clipes.
        trilha = pasta / "trilha.wav"
        audio.concatenar(ondas, trilha)
        lista = pasta / "lista.txt"
        lista.write_text("".join(f"file '{i}.mp4'\n" for i in range(len(partes))), encoding="utf-8")
        final = pasta / "final.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                        "-i", str(lista), "-i", str(trilha), "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", str(final)], check=True)
        final.replace(destino)


def gerar(livro: Livro, trechos: list[Trecho], cliente: HeyGenVideo, ao_progredir=print) -> list[Path]:
    if faltam := sorted({t.personagem for t in trechos if not t.avatar.strip()}):
        raise ValueError(f"configure avatares no livro.yaml para: {', '.join(faltam)}")
    if not shutil.which("ffmpeg"):
        raise ValueError("ffmpeg não encontrado")
    _, formato, motor = opcoes(livro)
    pasta = livro.dir_cache / "video"
    pasta.mkdir(parents=True, exist_ok=True)
    # Evita duas execuções criarem o mesmo clipe ou disputarem o estado.
    trava = pasta / "gerando.lock"
    try:
        lock = trava.open("x")
    except FileExistsError as e:
        raise ErroVideo(f"já existe uma geração em andamento; se ela foi encerrada à força, remova {trava}") from e
    try:
        por_cap = {}
        for i, t in enumerate(trechos, 1):
            destino = pasta / f"{t.chave}.mp4"
            estado_path = pasta / f"{t.chave}.json"
            estado = json.loads(estado_path.read_text()) if estado_path.exists() else {}
            if not destino.exists() or not destino.stat().st_size:
                if not estado.get("asset_id"):
                    estado["asset_id"] = cliente.enviar_audio(recortar(t))
                    _gravar(estado_path, estado)
                if not estado.get("video_id"):
                    if not estado.get("solicitado_em"):
                        estado["solicitado_em"] = time.time()
                        _gravar(estado_path, estado)
                    # A HeyGen só garante idempotência por 24 horas.
                    if time.time() - estado["solicitado_em"] > 23 * 3600:
                        raise ErroVideo(f"pedido sem ID há mais de 23h: confira a geração no HeyGen antes de alterar {estado_path}")
                    payload = {"type": "avatar", "avatar_id": t.avatar,
                               "audio_asset_id": estado["asset_id"], "aspect_ratio": formato,
                               "resolution": "1080p", "engine": {"type": motor},
                               "title": f"{livro.titulo} {t.cap} fala {t.ordem}"}
                    estado["video_id"] = cliente.criar(payload, t.chave)
                    _gravar(estado_path, estado)
                cliente.baixar(estado["video_id"], destino)
            por_cap.setdefault(t.cap, []).append((t, destino))
            ao_progredir(f"[{i}/{len(trechos)}] {t.cap} — {t.personagem}: pronto")
        finais = []
        for cap, itens in por_cap.items():
            final = livro.dir / "video" / f"{cap}.mp4"
            juntar([t for t, _ in itens], [p for _, p in itens], final, formato)
            finais.append(final)
        return finais
    finally:
        lock.close()
        trava.unlink()
