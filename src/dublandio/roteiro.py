"""Estágio 2: roteiro "Nome: fala" -> manifesto JSON com a voz de cada fala resolvida."""

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from dublandio.config import NARRADOR, Livro

# Prefixo só conta como personagem se parecer nome: até 30 caracteres e toda palavra
# começando com maiúscula ("Sra. Thorne"). Assim "Era assim: frio" continua narração.
_NOME = re.compile(r"[A-ZÀ-Ý][\w.À-ÿ-]*(?: [A-ZÀ-Ý][\w.À-ÿ-]*)*")
_MAX_NOME = 30


@dataclass
class Fala:
    ordem: int
    personagem: str
    voz: str
    texto: str


def _dividir(bloco: str) -> tuple[str, str]:
    if ":" in bloco:
        prefixo, resto = bloco.split(":", 1)
        prefixo = prefixo.strip()
        if len(prefixo) <= _MAX_NOME and _NOME.fullmatch(prefixo):
            return prefixo, resto
    return NARRADOR, bloco


def parse_roteiro(texto: str, livro: Livro) -> list[Fala]:
    falas: list[Fala] = []
    for bloco in re.split(r"\n\s*\n", texto):
        if not bloco.strip():
            continue
        nome, fala = _dividir(bloco.strip())
        fala = " ".join(fala.split())
        if not fala:
            continue
        personagem = livro.nome_canonico(nome)
        falas.append(Fala(len(falas) + 1, personagem, livro.voz(personagem), fala))
    return falas


def separar_livro(livro: Livro) -> list[Path]:
    """Gera livros/<slug>/manifesto/cap_NNN.json para cada roteiro. Sempre regenera."""
    livro.dir_manifesto.mkdir(parents=True, exist_ok=True)
    gerados = []
    for roteiro in sorted(livro.dir_roteiro.glob("cap_*.txt")):
        falas = parse_roteiro(roteiro.read_text(encoding="utf-8"), livro)
        destino = livro.dir_manifesto / f"{roteiro.stem}.json"
        destino.write_text(json.dumps([asdict(f) for f in falas], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        gerados.append(destino)
    return gerados


def ler_manifesto(path: Path) -> list[Fala]:
    return [Fala(**d) for d in json.loads(path.read_text(encoding="utf-8"))]


def contar_personagens(livro: Livro) -> Counter[str]:
    """Nº de falas de cada personagem em todos os manifestos do livro."""
    contagem: Counter[str] = Counter()
    for m in sorted(livro.dir_manifesto.glob("cap_*.json")):
        contagem.update(f.personagem for f in ler_manifesto(m))
    return contagem
