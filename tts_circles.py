#!/usr/bin/env python3
"""
Envia áudio pelo manifesto.json — escolhe automaticamente:
- Se OPENROUTER_API_KEY existe -> usa OpenRouter (mapa_vozes.json, voz por nome, PCM -> WAV)
- Se não -> usa HeyGen direto (mapa_vozes_heygen.json, voice_id, WAV direto)
Uso:
    export OPENROUTER_API_KEY="..."  # opcional
    export HEYGEN_API_KEY="..."      # obrigatório se não usar OpenRouter
    python3 tts_smart.py [stem_final]
"""
import os, sys, time, json, struct, subprocess
from pathlib import Path
import requests

MANIFESTO = Path("manifesto_circles.json")
SAIDA_DIR = Path("audio_gerado")
TEMP_DIR = SAIDA_DIR / ".temp_smart"

# --- Carrega .env ---
def _load_dotenv(path=".env"):
    if Path(path).exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and v and not os.getenv(k):
                    os.environ[k] = v
_load_dotenv()

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
HEYGEN_KEY = os.getenv("HEYGEN_API_KEY")

# --- Modo ---
if OPENROUTER_KEY:
    MODO = "openrouter"
    GUIA = Path("mapa_vozes.json")
    URL = "https://openrouter.ai/api/v1/audio/speech"
    MODEL = "heygen/heygen-voice-1-turbo"
    RESP_FORMAT = "pcm"
else:
    if not HEYGEN_KEY:
        print("ERRO: defina OPENROUTER_API_KEY ou HEYGEN_API_KEY")
        sys.exit(1)
    MODO = "heygen"
    GUIA = Path("mapa_vozes_heygen.json")
    URL = "https://api.heygen.com/v3/models/audio/tts"
    MODEL = "heygen-voice-1-turbo-free"  # mude se pagar

def _pcm_to_wav(data: bytes, rate: int = 44100, channels: int = 1, bits: int = 16) -> bytes:
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

def main(stem="manifesto"):
    if not MANIFESTO.exists():
        print(f"ERRO: {MANIFESTO} não encontrado")
        sys.exit(1)
    if not GUIA.exists():
        print(f"ERRO: {GUIA} não encontrado")
        sys.exit(1)

    manifesto = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    mapa = json.load(open(GUIA, encoding="utf-8"))

    SAIDA_DIR.mkdir(exist_ok=True)
    TEMP_DIR.mkdir(exist_ok=True)

    temp_files = []
    # Verifica arquivos de texto
    for reg in manifesto:
        arquivo = Path("textos_circles_limpos") / reg["arquivo"]
        reg["_path"] = arquivo
        if not arquivo.exists():
            print(f"[aviso] arquivo não encontrado, pulando: {arquivo}")

    for idx, reg in enumerate(manifesto, 1):
        arquivo = reg.get("_path")
        if not arquivo or not arquivo.exists():
            continue

        fala = arquivo.read_text(encoding="utf-8").strip()
        if not fala:
            continue

        personagem = reg.get("personagem", "Narrador")

        # Busca voz conforme modo
        if MODO == "openrouter":
            voz = mapa.get(personagem) or mapa.get("Narrador") or "lucian"
            payload = {
                "model": MODEL,
                "input": fala,
                "voice": voz,
                "response_format": RESP_FORMAT,
            }
            headers = {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"}
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
                    except:
                        pass
                    wav = _pcm_to_wav(raw, rate=rate, channels=channels)
                    temp_path = TEMP_DIR / f"{stem}_{idx:03d}.wav"
                    temp_path.write_bytes(wav)
                    temp_files.append(temp_path)
                    print(f"[{idx:03d}] {personagem} -> {voz} (OpenRouter) | {fala[:60]}...")
                else:
                    msg = resp.text
                    try:
                        msg = resp.json().get("error",{}).get("message", resp.text)
                    except:
                        pass
                    print(f"[erro] {idx:03d} {personagem} -> HTTP {resp.status_code}: {msg}")
            except Exception as e:
                print(f"[erro] {idx:03d} {personagem} -> {e}")
        else:  # heygen
            voice_id = mapa.get(personagem) or mapa.get("Narrador") or "83548de556df48ba8c09c42a57c51d85"
            payload = {
                "model": MODEL,
                "voice_id": voice_id,
                "text": fala,
                "language": "pt"
            }
            headers = {"X-Api-Key": HEYGEN_KEY, "Content-Type": "application/json"}
            try:
                resp = requests.post(URL, headers=headers, json=payload, timeout=120)
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    audio_url = data.get("audio_url")
                    if not audio_url:
                        print(f"[{idx:03d}] {personagem} -> sem audio_url")
                        continue
                    r = requests.get(audio_url, timeout=120)
                    r.raise_for_status()
                    temp_path = TEMP_DIR / f"{stem}_{idx:03d}.wav"
                    temp_path.write_bytes(r.content)
                    temp_files.append(temp_path)
                    print(f"[{idx:03d}] {personagem} -> {voice_id[:8]}... (HeyGen) | {fala[:60]}...")
                else:
                    msg = resp.text
                    try:
                        msg = resp.json().get("message", resp.text)
                    except:
                        pass
                    print(f"[erro] {idx:03d} {personagem} -> HTTP {resp.status_code}: {msg}")
            except Exception as e:
                print(f"[erro] {idx:03d} {personagem} -> {e}")
        time.sleep(0.3)

    if temp_files:
        final = SAIDA_DIR / f"{stem}.wav"
        if final.exists():
            final.unlink()
        lista = TEMP_DIR / f"{stem}_lista.txt"
        with open(lista, "w") as f:
            for p in temp_files:
                f.write(f"file '{p.resolve()}'\n")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(lista), "-c", "copy", str(final)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        for p in temp_files:
            p.unlink()
        lista.unlink()
        print(f"\n[juntado] {final.name} ({len(temp_files)} partes -> 1 arquivo) | modo={MODO}")
    else:
        print("\n[aviso] nenhum áudio gerado")

if __name__ == "__main__":
    stem = sys.argv[1] if len(sys.argv) > 1 else "manifesto"
    main(stem)
