"""OpenRouter: endpoint de TTS compatível com OpenAI, devolve PCM cru."""

import requests

from dublandio.audio import pcm_to_wav
from dublandio.tts.base import ErroTTS, Verificacao, erro_http

URL = "https://openrouter.ai/api/v1/audio/speech"
URL_CHAVE = "https://openrouter.ai/api/v1/key"  # validade e limite de gasto da chave
URL_CREDITOS = "https://openrouter.ai/api/v1/credits"  # saldo da conta
MODELO = "heygen/heygen-voice-1-turbo"
TIMEOUT = 120


def _formato(content_type: str) -> tuple[int, int]:
    rate, channels = 44100, 1
    for parte in content_type.split(";"):
        chave, _, valor = parte.strip().partition("=")
        if chave == "rate" and valor.isdigit():
            rate = int(valor)
        elif chave == "channels" and valor.isdigit():
            channels = int(valor)
    return rate, channels


class OpenRouter:
    nome = "openrouter"

    def __init__(self, chave: str):
        self._chave = chave

    def sintetizar(self, texto: str, voz: str, idioma: str) -> bytes:
        try:
            resp = requests.post(
                URL,
                headers={"Authorization": f"Bearer {self._chave}"},
                json={"model": MODELO, "input": texto, "voice": voz, "response_format": "pcm"},
                timeout=TIMEOUT,
            )
        except requests.RequestException as e:
            raise ErroTTS(str(e), retentavel=True) from e
        if resp.status_code != 200:
            try:
                msg = resp.json().get("error", {}).get("message", resp.text)
            except ValueError:
                msg = resp.text
            raise erro_http(resp.status_code, msg)
        rate, channels = _formato(resp.headers.get("Content-Type", ""))
        return pcm_to_wav(resp.content, rate=rate, channels=channels)

    def verificar(self) -> Verificacao:
        """Confere a chave e o saldo sem gastar crédito."""
        cabecalho = {"Authorization": f"Bearer {self._chave}"}
        try:
            chave = requests.get(URL_CHAVE, headers=cabecalho, timeout=30)
            if chave.status_code in (401, 403):
                return Verificacao("invalida")
            if chave.status_code != 200:
                return Verificacao("indisponivel", f"HTTP {chave.status_code}")
            restante = (chave.json().get("data") or {}).get("limit_remaining")
            if restante is not None and restante <= 0:
                return Verificacao("sem_credito", "a chave atingiu o limite de gasto definido no OpenRouter", saldo=0.0)
            creditos = requests.get(URL_CREDITOS, headers=cabecalho, timeout=30)
            dados = (creditos.json().get("data") or {}) if creditos.status_code == 200 else {}
        except (requests.RequestException, ValueError) as e:
            return Verificacao("indisponivel", str(e))
        if "total_credits" not in dados:  # saldo é só um extra: a chave já foi aceita
            return Verificacao("ok")
        saldo = float(dados["total_credits"] or 0) - float(dados.get("total_usage") or 0)
        if saldo <= 0:
            return Verificacao("sem_credito", saldo=saldo)
        return Verificacao("ok", saldo=saldo)
