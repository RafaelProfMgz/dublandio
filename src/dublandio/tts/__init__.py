"""Provedores de TTS. Use `criar_provedor(nome)`."""

import os

from dublandio.tts.base import ErroConfig, ErroTTS, Provedor, Verificacao, Voz
from dublandio.tts.heygen import HeyGen
from dublandio.tts.openrouter import OpenRouter

_CLASSES = {"openrouter": (OpenRouter, "OPENROUTER_API_KEY"), "heygen": (HeyGen, "HEYGEN_API_KEY")}
VARIAVEIS = {nome: variavel for nome, (_, variavel) in _CLASSES.items()}

__all__ = ["VARIAVEIS", "ErroConfig", "ErroTTS", "Provedor", "Verificacao", "Voz", "criar_provedor"]


def criar_provedor(nome: str) -> Provedor:
    if nome not in _CLASSES:
        raise ErroConfig(f"provedor desconhecido: {nome}")
    classe, variavel = _CLASSES[nome]
    chave = os.getenv(variavel)
    if not chave:
        raise ErroConfig(f"defina {variavel} no .env para usar o provedor {nome}")
    return classe(chave)
