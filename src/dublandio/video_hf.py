"""Foto + WAV existente -> vídeo em uma demo pública SadTalker do Hugging Face."""

import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import wave
from pathlib import Path

from dublandio.audio import executavel_ffmpeg
from dublandio.video import ErroVideo

SPACE_PADRAO = "henrybit/SadTalker-Demo"


def montar_com_audio_original(render: Path, audio: Path, destino: Path) -> None:
    """Mantém a imagem renderizada e substitui a trilha pelo WAV aprovado."""
    with wave.open(str(audio)) as wav:
        duracao = wav.getnframes() / wav.getframerate()
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destino.parent) as pasta:
        temporario = Path(pasta) / "final.mp4"
        subprocess.run([
            executavel_ffmpeg(), "-y", "-loglevel", "error", "-i", str(render), "-i", str(audio),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
            "-t", str(duracao), "-movflags", "+faststart", str(temporario),
        ], check=True)
        temporario.replace(destino)


def gerar_video_hf(
    imagem: Path, audio: Path, destino: Path, token: str, space: str = SPACE_PADRAO,
    ao_progredir=print, limite_segundos: float = 1200,
) -> Path:
    """Usa só a cota existente do Space; não contrata nem modifica hardware."""
    for arquivo in (imagem, audio):
        if not arquivo.is_file():
            raise FileNotFoundError(f"arquivo não encontrado: {arquivo}")
    if not token:
        raise ValueError("HF_TOKEN não definido no .env")
    executavel_ffmpeg()
    try:
        with wave.open(str(audio)) as wav:
            if not wav.getnframes():
                raise ValueError("o WAV está vazio")
    except (wave.Error, EOFError) as e:
        raise ValueError("o áudio precisa ser um WAV PCM legível") from e
    assinatura = hashlib.sha256(
        imagem.read_bytes() + audio.read_bytes() + (space + ":full:still:0:1").encode()
    ).hexdigest()
    cache = destino.parent / ".hf-cache" / assinatura
    estado_path = cache / "estado.json"
    estado = json.loads(estado_path.read_text()) if estado_path.exists() else {}
    if destino.exists():
        if estado.get("final") == str(destino.resolve()) and destino.stat().st_size:
            return destino
        raise ValueError("o destino já existe; escolha outro --nome para preservar o vídeo")
    cache.mkdir(parents=True, exist_ok=True)
    render = Path(estado["render"]) if estado.get("render") else None
    if not render or not render.is_file():
        from gradio_client import Client, handle_file

        try:
            cliente = Client(space, token=token, download_files=cache, analytics_enabled=False, verbose=False)
            job = cliente.submit(
                handle_file(str(imagem.resolve())), handle_file(str(audio.resolve())),
                "full", True, 0, 1.0, api_name="/generate",
            )
            inicio, anterior = time.monotonic(), None
            while not job.done():
                if time.monotonic() - inicio > limite_segundos:
                    job.cancel()
                    raise ErroVideo("a espera excedeu o limite; confira a demo antes de tentar novamente")
                status = str(job.status().code)
                if status != anterior:
                    ao_progredir(f"Hugging Face: {status}")
                    anterior = status
                time.sleep(2)
            resultado = job.result()
            caminho = resultado.get("video") if isinstance(resultado, dict) else resultado
            if isinstance(caminho, dict):
                caminho = caminho.get("path")
            if not isinstance(caminho, str) or not Path(caminho).is_file():
                raise ErroVideo("a demo não devolveu um arquivo de vídeo")
            render = Path(caminho)
            estado = {"space": space, "render": str(render.resolve()), "assinatura": assinatura}
            estado_path.write_text(json.dumps(estado, ensure_ascii=False, indent=2) + "\n")
        except ErroVideo:
            raise
        except Exception as e:
            detalhe = str(e).replace(token, "[token oculto]")
            raise ErroVideo(f"a demo Hugging Face não concluiu a geração: {detalhe}") from e
    montar_com_audio_original(render, audio, destino)
    estado["final"] = str(destino.resolve())
    estado_path.write_text(json.dumps(estado, ensure_ascii=False, indent=2) + "\n")
    return destino
