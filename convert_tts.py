#!/usr/bin/env python3
"""
Converte .txt -> .mp3 usando HeyGen Voice Turbo via OpenRouter TTS API.
Coloque seus .txt em textos_para_tts/ e rode: python3 convert_tts.py
"""
import os
import sys
import time
from pathlib import Path


def _load_dotenv(path=".env"):
    if Path(path).exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                os.environ.setdefault(k, v)

_load_dotenv()

import requests

# Configurações
TEXTO_DIR = Path("textos_para_tts")
SAIDA_DIR = Path("audio_gerado")
API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "heygen/heygen-voice-1-turbo"
VOICE = os.getenv("TTS_VOICE", "weston")  # nadine, tabitha, bram, gareth, noelle, meredith, sabrina, lucian, weston, vincent
RESPONSE_FORMAT = "pcm"  # pcm (HeyGen só aceita pcm; vamos salvar como .wav)

URL = "https://openrouter.ai/api/v1/audio/speech"


def _pcm_to_wav(data: bytes, rate: int = 44100, channels: int = 1, bits: int = 16) -> bytes:
    import struct
    byte_rate = rate * channels * bits // 8
    block_align = channels * bits // 8
    data_size = len(data)
    header = b"RIFF"
    header += struct.pack("<I", 36 + data_size)
    header += b"WAVE"
    header += b"fmt "
    header += struct.pack("<I", 16)
    header += struct.pack("<H", 1)           # PCM
    header += struct.pack("<H", channels)
    header += struct.pack("<I", rate)
    header += struct.pack("<I", byte_rate)
    header += struct.pack("<H", block_align)
    header += struct.pack("<H", bits)
    header += b"data"
    header += struct.pack("<I", data_size)
    return header + data


def _chunk_text(text: str, max_len: int = 4000) -> list:
    chunks = []
    current = []
    current_len = 0
    for line in text.splitlines():
        line_len = len(line) + 1
        if current_len + line_len > max_len and current:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return chunks


def converter(arquivo_txt: Path):
    texto = arquivo_txt.read_text(encoding="utf-8")
    if not texto.strip():
        print(f"[pulo] {arquivo_txt.name} está vazio.")
        return

    chunks = _chunk_text(texto)
    if not chunks:
        return

    for idx, chunk in enumerate(chunks):
        if len(chunks) > 1:
            nome_saida = f"{arquivo_txt.stem}_{idx+1:02d}.wav"
        else:
            nome_saida = arquivo_txt.stem + ".wav"
        caminho_saida = SAIDA_DIR / nome_saida

        if caminho_saida.exists():
            print(f"[pulo] {nome_saida} já existe.")
            continue

        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": MODEL,
            "input": chunk,
            "voice": VOICE,
            "response_format": RESPONSE_FORMAT,
        }

        try:
            resp = requests.post(URL, headers=headers, json=payload, timeout=120)
            if resp.status_code == 200:
                raw = resp.content
                ct = resp.headers.get("Content-Type", "audio/pcm")
                rate = 44100
                channels = 1
                try:
                    for part in ct.split(";"):
                        part = part.strip()
                        if part.startswith("rate="):
                            rate = int(part.split("=", 1)[1])
                        elif part.startswith("channels="):
                            channels = int(part.split("=", 1)[1])
                except Exception:
                    pass
                wav_data = _pcm_to_wav(raw, rate=rate, channels=channels)
                caminho_saida.write_bytes(wav_data)
                print(f"[ok] {nome_saida} ({len(wav_data)} bytes, {rate}Hz, {channels}ch)")
            else:
                try:
                    err = resp.json()
                    msg = err.get("error", {}).get("message", resp.text)
                except Exception:
                    msg = resp.text
                print(f"[erro] {arquivo_txt.name} [{idx+1}] -> HTTP {resp.status_code}: {msg}")
        except Exception as e:
            print(f"[erro] {arquivo_txt.name} [{idx+1}] -> {e}")


def main():
    if not API_KEY:
        print("ERRO: Defina OPENROUTER_API_KEY (export OPENROUTER_API_KEY=sk-...)")
        sys.exit(1)

    SAIDA_DIR.mkdir(exist_ok=True)
    TEXTO_DIR.mkdir(exist_ok=True)

    arquivos = sorted(TEXTO_DIR.glob("*.txt"))
    if not arquivos:
        print(f"Nenhum .txt encontrado em {TEXTO_DIR}/")
        return

    for f in arquivos:
        converter(f)
        time.sleep(0.5)  # leve pausa entre requisições


if __name__ == "__main__":
    main()
