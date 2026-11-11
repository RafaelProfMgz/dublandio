#!/bin/bash
# Roda tts_smart.py um capítulo por vez (gerando audio_gerado/cap_XXX.wav)
set -e

for f in textos_circles/*.txt; do
    stem=$(basename "$f" .txt)
    echo "[processando] $stem"
    
    # Criar manifesto apenas para este capítulo
    python3 -c "
import json
m = json.load(open('manifesto_circles.json'))
cap = [r for r in m if r.get('origem_cap') == '$stem' or r['arquivo'].startswith('$stem')]
json.dump(cap, open('manifesto.json','w'), indent=2, ensure_ascii=False)
print('Falas para $stem:', len(cap))
"
    
    # Garante que os arquivos limpos existem (se já foram apagados, regenerar)
    # Se não houver arquivos limpos, pular ou avisar
    if [ ! -f "textos_circles_limpos/${stem}_001.txt" ]; then
        echo "[aviso] Arquivos limpos do $stem não encontrados. Pule ou regenere com preparar_circles.py"
        continue
    fi
    
    # Rodar TTS para este capítulo
    unset OPENROUTER_API_KEY
    python3 tts_smart.py "$stem"
    
done

echo "[ok] Todos os capítulos processados (um .wav por capítulo)"
