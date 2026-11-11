#!/usr/bin/env python3
import json, re
from pathlib import Path
from collections import Counter

MANIFESTO = Path("manifesto_circles.json")
ORIGEM = Path("textos_circles")

mapa = json.load(open("mapa_vozes.json", encoding="utf-8"))

registros = []
ordem = 1

for txt_path in sorted(ORIGEM.glob("cap_*.txt")):
    stem = txt_path.stem
    texto = txt_path.read_text(encoding="utf-8")
    blocos = [b.strip() for b in texto.split("\n\n") if b.strip()]
    for bloco in blocos:
        if ":" in bloco:
            nome_raw = bloco.split(":", 1)[0].strip()
            fala = bloco.split(":", 1)[1].strip()
        else:
            nome_raw = "Narrador"
            fala = bloco
        
        # Corrigir nomes errados
        nome = nome_raw
        if nome == "Ele":
            nome = "Fonoti"
        elif nome == "Ela":
            nome = "Fa Yuiry"
        elif nome == "Green":
            nome = "Narrador"
        elif nome == "Side":
            nome = "Narrador"
        elif len(nome) > 30:
            nome = "Narrador"
        
        # Normalizar nomes que são apenas primeira parte
        if nome == "Leilani":
            # Se o texto começa com Leilani Reyes, é narrador (descreve ação)
            if fala.startswith("Reyes assumiu") or fala.startswith("Reyes"):
                nome = "Narrador"
        
        voz = mapa.get(nome) or mapa.get("Narrador") or "lucian"
        
        registros.append({
            "ordem": ordem,
            "arquivo": f"{stem}_{ordem:03d}.txt",
            "personagem": nome,
            "voz_ia": voz,
            "texto": fala,
            "origem_cap": stem
        })
        ordem += 1

MANIFESTO.write_text(json.dumps(registros, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"[ok] {len(registros)} registros -> {MANIFESTO}")
c = Counter(r["personagem"] for r in registros)
print("Top:", dict(c.most_common(8)))
