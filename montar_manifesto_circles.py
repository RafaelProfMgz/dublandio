#!/usr/bin/env python3
"""
Processa textos_circles/*.txt (formato Nome: fala \n\n) e gera:
- textos_circles_limpos/*.txt (um por fala)
- manifesto_circles.json (indexado, com voz preservada do mapa)
"""
import os, sys, json, re
from pathlib import Path

MAPA = json.load(open("mapa_vozes.json", encoding="utf-8"))
ORIGEM = Path("textos_circles")
SAIDA = Path("textos_circles_limpos")
MANIFESTO = Path("manifesto_circles.json")
SAIDA.mkdir(exist_ok=True)

registros = []
ordem_global = 1

for txt_path in sorted(ORIGEM.glob("cap_*.txt")):
    stem = txt_path.stem  # cap_001
    texto = txt_path.read_text(encoding="utf-8")
    blocos = [b.strip() for b in texto.split("\n\n") if b.strip()]
    
    for idx, bloco in enumerate(blocos, 1):
        if ":" not in bloco:
            nome = "Narrador"
            fala = bloco
        else:
            nome = bloco.split(":", 1)[0].strip()
            fala = bloco.split(":", 1)[1].strip()
        
        # Buscar voz no mapa (OpenRouter nomes) — preservar seleção
        voz = MAPA.get(nome) or MAPA.get("Narrador") or "lucian"
        
        out_name = f"{stem}_{idx:03d}.txt"
        out_path = SAIDA / out_name
        out_path.write_text(fala, encoding="utf-8")
        
        registros.append({
            "ordem": ordem_global,
            "arquivo": out_name,
            "personagem": nome,
            "voz_ia": voz,
            "texto": fala,
            "origem_cap": stem
        })
        ordem_global += 1

MANIFESTO.write_text(json.dumps(registros, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"[ok] {len(registros)} falas -> {SAIDA}")
print(f"[ok] manifesto -> {MANIFESTO}")
print(f"[info] Voze preservadas do mapa_vozes.json (OpenRouter): {dict((k,v) for k,v in MAPA.items() if k in ('Narrador','Bright Noa','Fa Yuiry','Kamille','Quattro','Emma','Fonoti','Reyes','Delgado')[:5])}")
