#!/usr/bin/env python3
"""
Após rodar convert_tts.py, junta as partes e remove elas,
deixando apenas o arquivo combinado por capítulo.
"""
import subprocess
from pathlib import Path

TEXTO_DIR = Path("textos_para_tts")
SAIDA_DIR = Path("audio_gerado")

def juntar_e_limpar(stem: str):
    # Encontrar partes ordenadas
    partes = sorted(SAIDA_DIR.glob(f"{stem}_??.wav"))
    if not partes:
        # Se só tem arquivo único, não faz nada
        return
    # Juntar
    temp = SAIDA_DIR / f"{stem}_temp.wav"
    # Criar lista para ffmpeg concat
    lista = SAIDA_DIR / f"{stem}_lista.txt"
    with open(lista, "w") as f:
        for p in partes:
            f.write(f"file '{p.resolve()}'\n")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(lista),
        "-c", "copy", str(temp)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    # Substituir partes pelo combinado (nome limpo sem sufixo)
    final = SAIDA_DIR / f"{stem}.wav"
    # Se já existe final antigo, remover
    if final.exists() and final != temp:
        final.unlink()
    temp.rename(final)
    # Remover partes
    for p in partes:
        p.unlink()
    lista.unlink()
    print(f"[juntado] {stem}.wav ({len(partes)} partes -> 1)")

def main():
    for txt in sorted(TEXTO_DIR.glob("*.txt")):
        stem = txt.stem
        juntar_e_limpar(stem)

if __name__ == "__main__":
    main()
