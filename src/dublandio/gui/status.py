"""Situação de cada capítulo de um livro: o que já existe e quanto falta sintetizar."""

import re
from pathlib import Path

from dublandio.config import NARRADOR, Livro
from dublandio.roteiro import contar_personagens, ler_manifesto
from dublandio.sintetizar import parte_em_cache

CAP = re.compile(r"cap_\d{3}")


def _mtime(p: Path) -> float | None:
    return p.stat().st_mtime if p.exists() else None


def capitulos(livro: Livro) -> list[str]:
    nomes = {p.stem for pasta, ext in ((livro.dir_roteiro, "txt"), (livro.dir_manifesto, "json"), (livro.dir_audio, "wav"))
             for p in pasta.glob(f"cap_*.{ext}") if CAP.fullmatch(p.stem)}
    return sorted(nomes)


def status_capitulo(livro: Livro, cap: str) -> dict:
    roteiro = livro.dir_roteiro / f"{cap}.txt"
    manifesto = livro.dir_manifesto / f"{cap}.json"
    audio = livro.dir_audio / f"{cap}.wav"
    t_roteiro, t_manifesto, t_audio = _mtime(roteiro), _mtime(manifesto), _mtime(audio)

    falas = []
    if t_manifesto is not None:
        for f in ler_manifesto(manifesto):
            falas.append({"ordem": f.ordem, "personagem": f.personagem, "em_cache": parte_em_cache(livro, cap, f) is not None})

    return {
        "cap": cap,
        "numero": int(cap.removeprefix("cap_")),
        "tem_roteiro": t_roteiro is not None,
        "tem_manifesto": t_manifesto is not None,
        "tem_audio": t_audio is not None,
        # Roteiro editado depois do último `separar` (que sempre regrava todos os manifestos).
        "manifesto_desatualizado": None not in (t_roteiro, t_manifesto) and t_roteiro > t_manifesto,
        "audio_versao": int(t_audio) if t_audio else None,
        "falas": falas,
        "pendentes": sum(not f["em_cache"] for f in falas),
    }


def resumo_livro(livro: Livro) -> dict:
    caps = capitulos(livro)
    return {
        "slug": livro.slug,
        "titulo": livro.titulo,
        "provedor": livro.provedor,
        "tem_origem": livro.origem is not None,
        "capitulos": len(caps),
        "com_audio": sum((livro.dir_audio / f"{c}.wav").exists() for c in caps),
    }


def vozes(livro: Livro) -> list[dict]:
    """Personagens por nº de falas, com a voz resolvida (mesma lógica de `dublandio vozes`)."""
    resultado = []
    for nome, n in contar_personagens(livro).most_common():
        try:
            voz = livro.voz(nome)
        except KeyError:
            voz = None
        resultado.append({
            "personagem": nome,
            "falas": n,
            "voz": voz,
            "voz_propria": nome == NARRADOR or livro.tem_voz_propria(nome),
        })
    return resultado
