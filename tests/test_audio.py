import shutil
import struct
import subprocess

import pytest

from dublandio.audio import concatenar, formato_wav, pcm_to_wav


def test_pcm_to_wav_header():
    wav = pcm_to_wav(b"\x00\x01" * 10, rate=24000)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    assert struct.unpack("<I", wav[4:8])[0] == 36 + 20
    assert struct.unpack("<I", wav[24:28])[0] == 24000
    assert wav[44:] == b"\x00\x01" * 10


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente")
def test_concatenar(tmp_path):
    partes = []
    for i in range(2):
        p = tmp_path / f"p{i}.wav"
        p.write_bytes(pcm_to_wav(b"\x00\x00" * 4410, rate=44100))
        partes.append(p)
    destino = tmp_path / "saida" / "cap.wav"
    concatenar(partes, destino)
    duracao = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(destino)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert float(duracao) == pytest.approx(0.2, abs=0.01)  # 2 partes de 0,1 s


def test_formato_wav_le_fmt_mesmo_depois_de_outro_chunk(tmp_path):
    wav = pcm_to_wav(b"\x00\x00" * 4, rate=24000)
    lista = b"LIST" + struct.pack("<I", 3) + b"abc\x00"  # chunk de tamanho ímpar, com preenchimento
    p = tmp_path / "a.wav"
    p.write_bytes(wav[:12] + lista + wav[12:])
    assert formato_wav(p) == (24000, 1, 16)
    (tmp_path / "b.wav").write_bytes(b"ID3 nao e wav")
    assert formato_wav(tmp_path / "b.wav") is None


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente")
def test_concatenar_formatos_diferentes(tmp_path):
    # Capítulo que trocou de provedor no meio: partes a 44,1 kHz e a 24 kHz.
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    a.write_bytes(pcm_to_wav(b"\x00\x00" * 4410, rate=44100))
    b.write_bytes(pcm_to_wav(b"\x00\x00" * 2400, rate=24000))
    destino = tmp_path / "cap.wav"
    concatenar([a, b], destino)
    sonda = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=sample_rate", "-of", "csv=p=0", str(destino)],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    assert sonda[0] == "44100"
    assert float(sonda[1]) == pytest.approx(0.2, abs=0.01)
