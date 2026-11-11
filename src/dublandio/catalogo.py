"""Catálogo de vozes do provedor, guardado em .cache/catalogo/<provedor>.json por um dia.

Listar vozes não gasta crédito, mas a lista da HeyGen tem milhares de vozes: o cache
evita buscar tudo de novo a cada consulta.
"""

import json
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from dublandio.tts.base import ErroConfig, Provedor, Voz

VALIDADE = 24 * 3600

# Código de idioma do livro.yaml -> nome que a HeyGen usa no catálogo.
IDIOMAS = {"pt": "Portuguese", "en": "English", "es": "Spanish", "fr": "French", "de": "German",
           "it": "Italian", "ja": "Japanese", "nl": "Dutch", "ru": "Russian"}


def carregar_catalogo(
    nome: str,
    fabrica: Callable[[str], Provedor],
    raiz: Path = Path("."),
    atualizar: bool = False,
    agora: Callable[[], float] = time.time,
) -> tuple[list[Voz], float]:
    """Vozes do provedor `nome` e o instante em que a lista foi buscada."""
    arquivo = raiz / ".cache" / "catalogo" / f"{nome}.json"
    if not atualizar and arquivo.exists() and agora() - arquivo.stat().st_mtime < VALIDADE:
        return [Voz(**v) for v in json.loads(arquivo.read_text(encoding="utf-8"))], arquivo.stat().st_mtime

    provedor = fabrica(nome)
    if not hasattr(provedor, "listar_vozes"):
        raise ErroConfig(f"o provedor {nome} não publica uma lista de vozes")
    vozes = sorted(provedor.listar_vozes(), key=lambda v: (v.idioma, v.nome.lower()))
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps([asdict(v) for v in vozes], ensure_ascii=False), encoding="utf-8")
    return vozes, arquivo.stat().st_mtime


def filtrar(vozes: list[Voz], idioma: str | None = None) -> list[Voz]:
    """Por idioma (código do livro, como "pt", ou nome, como "Portuguese"), sem diferenciar maiúsculas."""
    if not idioma:
        return vozes
    alvo = IDIOMAS.get(idioma.lower(), idioma).lower()
    return [v for v in vozes if alvo in v.idioma.lower()]
