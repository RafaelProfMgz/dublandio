#!/usr/bin/env python3
import os, sys, time, json, subprocess
from pathlib import Path

# Carrega .env igual ao convert_tts.py
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
                if k and v and not os.getenv(k):
                    os.environ[k] = v
_load_dotenv()

import requests

MAPA = json.load(open("mapa_vozes_heygen.json"))
API_KEY = os.getenv("HEYGEN_API_KEY")
URL = "https://api.heygen.com/v3/models/audio/tts"
MODEL = "heygen-voice-1-turbo-free"  # muda para "heygen-voice-1-turbo" se pagar

def processar_arquivo(txt_path: Path):
    stem = txt_path.stem
    texto = txt_path.read_text(encoding="utf-8")
    blocos = [b.strip() for b in texto.split("\n\n") if b.strip()]
    SAIDA_DIR = Path("audio_gerado")
    SAIDA_DIR.mkdir(exist_ok=True)
    TEMP_DIR = SAIDA_DIR / ".temp_heygen"
    TEMP_DIR.mkdir(exist_ok=True)
    temp_files = []
    
    for idx, bloco in enumerate(blocos):
        if ":" in bloco:
            nome = bloco.split(":", 1)[0].strip()
            fala = bloco.split(":", 1)[1].strip()
        else:
            nome = "Narrador"; fala = bloco
        
        voice_id = MAPA.get(nome, MAPA.get("Narrador", "83548de556df48ba8c09c42a57c51d85"))
        
        payload = {
            "model": MODEL,
            "voice_id": voice_id,
            "text": fala,
            "language": "pt"  # ou "en"; pode omitir para auto-detectar
        }
        try:
            resp = requests.post(URL, headers={"X-Api-Key": API_KEY, "Content-Type": "application/json"}, json=payload, timeout=120)
            if resp.status_code == 200:
                data = resp.json()["data"]
                audio_url = data["audio_url"]
                wav_path = TEMP_DIR / f"{stem}_{idx:03d}.wav"
                # Baixar WAV diretamente
                r = requests.get(audio_url, timeout=120)
                r.raise_for_status()
                wav_path.write_bytes(r.content)
                temp_files.append(wav_path)
                print(f"[ok] {stem} [{nome}->{voice_id}] ({len(r.content)} bytes)")
            else:
                msg = resp.json().get("message", resp.text) if resp.headers.get("content-type","").startswith("application/json") else resp.text
                print(f"[erro] {stem} [{nome}] -> HTTP {resp.status_code}: {msg}")
        except Exception as e:
            print(f"[erro] {stem} [{nome}] -> {e}")
        time.sleep(0.3)
    
    if temp_files:
        final = SAIDA_DIR / f"{stem}.wav"
        if final.exists():
            final.unlink()
        lista = TEMP_DIR / f"{stem}_lista.txt"
        with open(lista, "w") as f:
            for p in temp_files:
                f.write(f"file '{p.resolve()}'\n")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(final)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        for p in temp_files:
            p.unlink()
        lista.unlink()
        print(f"[juntado] {final.name} ({len(temp_files)} partes)")

def main():
    if not API_KEY:
        print("ERRO: exporte HEYGEN_API_KEY (export HEYGEN_API_KEY=...)")
        sys.exit(1)
    for txt in sorted(Path("textos_para_tts").glob("*.txt")):
        processar_arquivo(txt)
        time.sleep(0.5)

if __name__ == "__main__":
    main()
