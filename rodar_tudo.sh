#!/bin/bash
# ÚNICO COMANDO: separa falas, gera áudio, monta capítulo, apaga temp
set -e

echo "=== RODAR TUDO ==="

# 1. Se ainda não processou, processar todos capítulos (já feito, pular se existir)
if [ ! -f "manifesto_circles.json" ]; then
    echo "[1/4] Processando roteiros..."
    for f in textos_circles/*.txt; do
        stem=$(basename "$f" .txt)
        python3 processar_roterio.py "$f" "$stem"
    done
    # Montar manifesto combinado (exclui cap_001 se já feito)
    python3 montar_manifesto_circles.py
fi

# 2. Para cada capítulo (cap_002 a cap_010), gerar áudio
# Se quiser tudo junto, mude para: python3 tts_smart.py circles
for cap in cap_002 cap_003 cap_004 cap_005 cap_006 cap_007 cap_008 cap_009 cap_010; do
    echo "[2/4] Gerando áudio: $cap"
    
    # Criar manifesto do capítulo atual
    python3 -c "
import json
m = json.load(open('manifesto_circles.json'))
cap = [r for r in m if r.get('origem_cap') == '$cap' or r['arquivo'].startswith('$cap')]
json.dump(cap, open('manifesto.json','w'), indent=2, ensure_ascii=False)
"
    
    # Rodar TTS (HeyGen direto, remove OpenRouter)
    unset OPENROUTER_API_KEY
    python3 tts_smart.py "$cap"
    
    # 3. Juntar já feito pelo tts_smart.py; apenas confirmar
    if [ -f "audio_gerado/${cap}.wav" ]; then
        echo "[3/4] Capítulo montado: audio_gerado/${cap}.wav"
    fi
    
    # 4. Limpar temp deste capítulo
    rm -rf audio_gerado/.temp_smart/*
done

echo "=== TUDO PRONTO ==="
echo "Capítulos gerados:"
ls -lh audio_gerado/cap_*.wav 2>/dev/null || echo "Nenhum arquivo .wav encontrado (verifique se rodou)"
