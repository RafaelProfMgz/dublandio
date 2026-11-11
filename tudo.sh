#!/bin/bash
# Executa em ordem: processar roteiro -> gerar áudio (HeyGen direto ou OpenRouter)
set -e

# Se não passar argumento, usa circle.txt como padrão
ARQUIVO="${1:-textos_para_tts/circle.txt}"
STEM="${2:-$(basename "$ARQUIVO" .txt)}"

# 1. Processar roteiro (gera .txt limpos + manifesto)
echo "[1/2] Processando roteiro: $ARQUIVO -> $STEM"
python3 processar_roterio.py "$ARQUIVO" "$STEM"

# 2. Gerar áudio (prioriza HeyGen se não tiver OpenRouter)
echo "[2/2] Enviando para TTS (smart: OpenRouter se chave existir, senão HeyGen)"
unset OPENROUTER_API_KEY 2>/dev/null || true
python3 tts_smart.py "$STEM"

echo "[ok] Finalizado: audio_gerado/${STEM}.wav"
