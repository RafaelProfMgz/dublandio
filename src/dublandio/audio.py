"""Utilitários de áudio: PCM cru -> WAV e junção de partes com ffmpeg."""

import struct
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def executavel_ffmpeg() -> str:
    """Localiza também o FFmpeg do WinGet quando o processo herdou um PATH antigo."""
    if encontrado := shutil.which('ffmpeg'):
        return encontrado
    if os.name == 'nt':
        bases = [Path.home() / 'AppData' / 'Local']
        if local := os.getenv('LOCALAPPDATA'):
            bases.insert(0, Path(local))
        for base in dict.fromkeys(bases):
            winget = base / 'Microsoft' / 'WinGet'
            atalho = winget / 'Links' / 'ffmpeg.exe'
            if atalho.is_file():
                return str(atalho)
            for binario in sorted((winget / 'Packages').glob('Gyan.FFmpeg_*/*/bin/ffmpeg.exe')):
                if binario.is_file():
                    return str(binario)
    raise ValueError('FFmpeg não encontrado. Instale-o no Windows com '
                     'winget install --id Gyan.FFmpeg --exact ou use o Docker.')


def pcm_to_wav(pcm: bytes, rate: int = 44100, channels: int = 1, bits: int = 16) -> bytes:
    byte_rate = rate * channels * bits // 8
    block_align = channels * bits // 8
    cabecalho = (
        b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, rate, byte_rate, block_align, bits)
        + b"data" + struct.pack("<I", len(pcm))
    )
    return cabecalho + pcm


def formato_wav(caminho: Path) -> tuple[int, int, int] | None:
    """(taxa, canais, bits) do chunk fmt de um WAV; None se não for um WAV legível."""
    with open(caminho, "rb") as f:
        if f.read(12)[8:12] != b"WAVE":
            return None
        while len(cabecalho := f.read(8)) == 8:
            nome, tamanho = cabecalho[:4], struct.unpack("<I", cabecalho[4:])[0]
            if nome == b"fmt ":
                _, canais, taxa, _, _, bits = struct.unpack("<HHIIHH", f.read(16))
                return taxa, canais, bits
            f.seek(tamanho + tamanho % 2, 1)
    return None


def _converter(origem: Path, destino: Path, formato: tuple[int, int, int]) -> None:
    taxa, canais, bits = formato
    subprocess.run(
        [executavel_ffmpeg(), "-y", "-loglevel", "error", "-i", str(origem),
         "-ar", str(taxa), "-ac", str(canais), "-c:a", f"pcm_s{bits}le", str(destino)],
        check=True,
    )


def concatenar(partes: list[Path], destino: Path) -> None:
    """Junta WAVs na ordem dada (ffmpeg concat, sem recodificar).

    Partes em formato diferente da primeira (ex.: um capítulo que trocou de provedor no
    meio) são convertidas antes, porque o concat sem recodificar exige formato único.
    """
    ffmpeg = executavel_ffmpeg()
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as pasta:
        alvo = formato_wav(partes[0]) if partes else None
        uniformes = []
        for i, p in enumerate(partes):
            formato = formato_wav(p)
            if alvo and formato and formato != alvo:
                convertida = Path(pasta) / f"{i:05d}.wav"
                _converter(p, convertida, alvo)
                p = convertida
            uniformes.append(p)

        lista = Path(pasta) / "lista.txt"
        with open(lista, "w", encoding="utf-8") as f:
            for p in uniformes:
                caminho = p.resolve().as_posix().replace("'", r"'\''")
                f.write(f"file '{caminho}'\n")
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(destino)],
            check=True,
        )
