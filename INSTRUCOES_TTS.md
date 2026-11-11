PASTAS MONTADAS:
- textos_para_tts/  -> coloque seus .txt aqui
- audio_gerado/     -> áudios gerados aparecerão aqui

COMO USAR:
1. Pegue sua chave em https://openrouter.ai/settings/keys
2. Exporte: export OPENROUTER_API_KEY="sk-..."
3. Opcionalmente defina voz: export TTS_VOICE="nadine" (padrão)
4. Passe os .txt para textos_para_tts/
5. Rode: python3 convert_tts.py

OBS: o modelo usado é heygen/heygen-voice-1-turbo (free) via endpoint TTS do OpenRouter.
