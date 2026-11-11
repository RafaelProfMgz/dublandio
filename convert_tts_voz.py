#!/usr/bin/env python3
"""
Converte .txt com NOME: fala -> áudio por voz específica -> junta em 1 .wav.
Precisa do mapa: mapa_vozes.json (nome -> voz HeyGen)
"""
import os, sys, time, json, subprocess
from pathlib import Path
import requests

MAPA = json.load(open("mapa_vozes.json"))
API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "heygen/heygen-voice-1-turbo"
URL = "https://openrouter.ai/api/v1/audio/speech"
RESPONSE_FORMAT = "pcm"

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
    header += struct.pack("<H", 1)
    header += struct.pack("<H", channels)
    header += struct.pack("<I", rate)
    header += struct.pack("<I", byte_rate)
    header += struct.pack("<H", block_align)
    header += struct.pack("<H", bits)
    header += b"data"
    header += struct.pack("<I", data_size)
    return header + data

def processar_arquivo(txt_path: Path):
    stem = txt_path.stem
    texto = txt_path.read_text(encoding="utf-8")
    blocos = [b.strip() for b in texto.split("\n\n") if b.strip()]
    
    SAIDA_DIR = Path("audio_gerado")
    SAIDA_DIR.mkdir(exist_ok=True)
    TEMP_DIR = SAIDA_DIR / ".temp"
    TEMP_DIR.mkdir(exist_ok=True)
    
    arquivos_temp = []
    
    for idx, bloco in enumerate(blocos):
        if ":" in bloco:
            nome = bloco.split(":", 1)[0].strip()
            fala = bloco.split(":", 1)[1].strip()
        else:
            nome = "Narrador"
            fala = bloco
        
        voz = MAPA.get(nome, "weston")
        
        # Segurança: se fala muito grande, pode falhar; mas assumimos bloco pequeno aqui
        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": MODEL,
            "input": fala,
            "voice": voz,
            "response_format": RESPONSE_FORMAT,
        }
        
        try:
            resp = requests.post(URL, headers=headers, json=payload, timeout=120)
            if resp.status_code == 200:
                raw = resp.content
                ct = resp.headers.get("Content-Type", "audio/pcm")
                rate = 44100; channels = 1
                try:
                    for part in ct.split(";"):
                        part = part.strip()
                        if part.startswith("rate="):
                            rate = int(part.split("=", 1)[1])
                        elif part.startswith("channels="):
                            channels = int(part.split("=", 1)[1])
                except Exception:
                    pass
                wav = _pcm_to_wav(raw, rate=rate, channels=channels)
                temp_path = TEMP_DIR / f"{stem}_{idx:03d}.wav"
                temp_path.write_bytes(wav)
                arquivos_temp.append(temp_path)
                print(f"[ok] {stem} [{nome}->{voz}] ({len(wav)} bytes)")
            else:
                try:
                    msg = resp.json().get("error",{}).get("message", resp.text)
                except:
                    msg = resp.text
                print(f"[erro] {stem} [{nome}->{voz}] -> HTTP {resp.status_code}: {msg}")
        except Exception as e:
            print(f"[erro] {stem} [{nome}->{voz}] -> {e}")
        time.sleep(0.3)
    
    if arquivos_temp:
        final = SAIDA_DIR / f"{stem}.wav"
        # Se já existe final anterior (do convert_tts antigo), remove
        if final.exists():
            final.unlink()
        lista = TEMP_DIR / f"{stem}_lista.txt"
        with open(lista, "w") as f:
            for p in arquivos_temp:
                f.write(f"file '{p.resolve()}'\n")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(lista), "-c", "copy", str(final)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        # Limpar temp
        for p in arquivos_temp:
            p.unlink()
        lista.unlink()
        print(f"[juntado] {final.name} ({len(arquivos_temp)} partes -> 1 arquivo)")

def main():
    if not API_KEY:
        print("ERRO: defina OPENROUTER_API_KEY")
        sys.exit(1)
    for txt in sorted(Path("textos_para_tts").glob("*.txt")):
        processar_arquivo(txt)
        time.sleep(0.5)

if __name__ == "__main__":
    main()
