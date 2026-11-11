"""HeyGen: API direta; devolve uma URL de onde o WAV é baixado."""

import re

import requests

from dublandio.tts.base import ErroTTS, Verificacao, Voz, erro_http

URL = "https://api.heygen.com/v3/models/audio/tts"
URL_VOZES = "https://api.heygen.com/v2/voices"  # a v3 pagina de 20 em 20; a v2 traz todas
# Uma voz só: resposta curta para conferir a chave. Endpoints de conta pedem o escopo account:read,
# que chaves só de síntese não têm.
URL_CONFERIR = "https://api.heygen.com/v3/voices?limit=1"
MODELO = "heygen-voice-1-turbo-free"
TIMEOUT = 120
# 429 da cota diária ("used all 200,000 free Turbo characters for today"): só volta no dia seguinte.
_COTA = re.compile(r"used all|for today|quota", re.IGNORECASE)


class HeyGen:
    nome = "heygen"

    def __init__(self, chave: str):
        self._chave = chave

    def sintetizar(self, texto: str, voz: str, idioma: str) -> bytes:
        try:
            resp = requests.post(
                URL,
                headers={"X-Api-Key": self._chave},
                json={"model": MODELO, "voice_id": voz, "text": texto, "language": idioma},
                timeout=TIMEOUT,
            )
            if resp.status_code != 200:
                try:
                    msg = resp.json().get("message", resp.text)
                except ValueError:
                    msg = resp.text
                if resp.status_code == 429 and _COTA.search(msg):
                    raise ErroTTS(
                        f"a cota diária da HeyGen para o modelo {MODELO} acabou; ela renova amanhã "
                        f"(as falas já geradas ficam no cache). Resposta da HeyGen: {msg}",
                        interromper=True, motivo="cota",
                    )
                raise erro_http(resp.status_code, msg)
            audio_url = (resp.json().get("data") or {}).get("audio_url")
            if not audio_url:
                raise ErroTTS("resposta sem audio_url", retentavel=True)
            audio = requests.get(audio_url, timeout=TIMEOUT)
        except requests.RequestException as e:
            raise ErroTTS(str(e), retentavel=True) from e
        if audio.status_code != 200:
            raise erro_http(audio.status_code, "falha ao baixar o áudio")
        return audio.content

    def verificar(self) -> Verificacao:
        """Confere a chave sem gastar crédito. A cota diária do modelo gratuito não aparece aqui:
        só se descobre quando uma síntese esbarra nela."""
        try:
            resp = requests.get(URL_CONFERIR, headers={"X-Api-Key": self._chave}, timeout=30)
        except requests.RequestException as e:
            return Verificacao("indisponivel", str(e))
        if resp.status_code == 401:
            return Verificacao("invalida")
        if resp.status_code == 403:
            return Verificacao("invalida", "a chave não tem permissão para vozes e síntese")
        if resp.status_code != 200:
            return Verificacao("indisponivel", f"HTTP {resp.status_code}")
        return Verificacao("ok")

    def listar_vozes(self) -> list[Voz]:
        try:
            resp = requests.get(URL_VOZES, headers={"X-Api-Key": self._chave}, timeout=TIMEOUT)
        except requests.RequestException as e:
            raise ErroTTS(str(e), retentavel=True) from e
        if resp.status_code != 200:
            raise erro_http(resp.status_code, "falha ao listar as vozes")
        return [
            Voz(
                id=v["voice_id"],
                nome=(v.get("name") or v["voice_id"]).strip(),
                idioma=v.get("language") or "",
                genero=v.get("gender") or "",
                amostra=v.get("preview_audio") or None,
            )
            for v in (resp.json().get("data") or {}).get("voices") or []
            if v.get("voice_id")
        ]
