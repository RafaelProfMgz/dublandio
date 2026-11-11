#!/bin/bash
# UM ÚNICO COMANDO — passa a pasta ou arquivo, ele faz tudo:
# separa falas → gera áudio → junta capítulo → apaga temp → proximo
set -e

PASTA="${1:-textos_para_tts}"
echo "=== INICIANDO: $PASTA ==="

for f in $PASTA/*.txt; do
    [ -f "$f" ] || continue
    stem=$(basename "$f" .txt)
    
    echo "--- Processando: $stem ---"
    
    # 1. Se ainda não está separado em falas, processar
    # (se já tem \n\n entre falas, processar_roterio já funciona)
    python3 processar_roterio.py "$f" "$stem"
    
    # 2. Criar manifesto apenas para este capítulo (lê de textos_para_tts/ ou textos_circles_limpos/)
    # Se o arquivo limpo está em textos_para_tts/ (do preparar_vol1), usar direto
    # Se está em textos_circles_limpos/, usar de lá. Vamos tentar ambos.
    
    # Primeiro tenta gerar manifesto do arquivo limpo gerado
    # Se processar_roterio gerou em textos_para_tts/, usar de lá
    # Senão, usar textos_circles_limpos/
    
    if [ -d "textos_para_tts" ]; then
        # Se processar_roterio gerou arquivos com stem, eles estão lá
        # Criamos manifesto filtrando pelo stem
        python3 -c "
import json, re
from pathlib import Path
m = []
for p in sorted(Path('textos_para_tts').glob('${stem}_*.txt')):
    texto = p.read_text(encoding='utf-8')
    # Extrair nome do arquivo (ex: cap_002_001.txt)
    # Se o arquivo contém Nome: fala, extrair; senão usar arquivo como fala pura
    if ':' in texto:
        nome = texto.split(':', 1)[0].strip()
        fala = texto.split(':', 1)[1].strip()
    else:
        nome = 'Narrador'
        fala = texto
    voz_map = json.load(open('mapa_vozes.json'))
    voz = voz_map.get(nome) or voz_map.get('Narrador') or 'lucian'
    m.append({
        'ordem': len(m)+1,
        'arquivo': p.name,
        'personagem': nome,
        'voz_ia': voz,
        'texto': fala,
        'origem_cap': '$stem'
    })
json.dump(m, open('manifesto.json','w'), indent=2, ensure_ascii=False)
print('Manifesto criado para $stem:', len(m), 'falas')
"
    fi
    
    # 3. Gerar áudio (HeyGen direto)
    echo "[TTS] Gerando áudio para $stem ..."
    unset OPENROUTER_API_KEY
    python3 tts_smart.py "$stem"
    
    # 4. Verificar se .wav foi gerado; se sim, confirmar
    if [ -f "audio_gerado/${stem}.wav" ]; then
        echo "[OK] Capítulo montado: audio_gerado/${stem}.wav"
    else
        echo "[AVISO] Não gerou audio_gerado/${stem}.wav (pode estear em andamento)"
    fi
    
    # 5. Limpar temp deste capítulo
    rm -rf audio_gerado/.temp_smart/*
done

echo "=== TUDO FINALIZADO ==="
echo "Áudios em: audio_gerado/"
echo "Arquivos limpos mantidos em: textos_para_tts/"
