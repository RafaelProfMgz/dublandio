"""Importação de roteiro, vozes e fotos para um projeto de vídeo, sem chamadas pagas."""

import hashlib
import re
import tempfile
from collections import Counter
from pathlib import Path

import yaml

from dublandio import avatares
from dublandio.config import Livro, PROVEDORES, ler_livro
from dublandio.novo import slugificar
from dublandio.roteiro import parse_roteiro, separar_livro


def analisar_roteiro(texto: str) -> dict:
    """Aceita falas por linha ou por parágrafo; texto sem personagem é narração."""
    texto = texto.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n').strip()
    texto = re.sub(r'\n(?=[A-ZÀ-Ý][\w.À-ÿ-]*(?: [A-ZÀ-Ý][\w.À-ÿ-]*)*\s*:)', '\n\n', texto)
    texto = re.sub(r'\n(?:[ \t]*\n)+', '\n\n', texto)
    base = Livro('previa', 'Prévia', None, 'heygen', vozes={'heygen': {'Narrador': 'previa'}})
    falas = parse_roteiro(texto, base)
    if not falas:
        raise ValueError('envie um roteiro com pelo menos uma fala')
    contagem = Counter(f.personagem for f in falas)
    return {'texto': texto + '\n', 'total_falas': len(falas),
            'personagens': [{'nome': nome, 'falas': n} for nome, n in contagem.items()]}


def criar_projeto(raiz: Path, titulo: str, roteiro: str, personagens: list[dict],
                  provedor: str = 'heygen') -> Livro:
    """Valida tudo em pasta temporária; só publica o livro completo. Não gera áudio."""
    titulo = titulo.strip()
    slug = slugificar(titulo)
    if not titulo or not slug:
        raise ValueError('dê um título ao vídeo')
    if provedor not in PROVEDORES:
        raise ValueError('provedor inválido')
    destino = raiz / 'livros' / slug
    if destino.exists():
        raise ValueError(f"já existe um livro '{slug}'; escolha outro título")
    previa = analisar_roteiro(roteiro)
    nomes = [p['nome'] for p in previa['personagens']]
    fichas = {p['nome'].strip(): p for p in personagens}
    if len(fichas) != len(personagens):
        raise ValueError('há personagens repetidos')
    if set(fichas) != set(nomes):
        raise ValueError('envie exatamente os personagens identificados no roteiro: ' + ', '.join(nomes))
    for nome, ficha in fichas.items():
        if not ficha['voz'].strip():
            raise ValueError(f'escolha a voz de {nome}')
        if not ficha['avatar']:
            raise ValueError(f'envie o avatar de {nome}')
        id_ = hashlib.sha256(ficha['avatar']).hexdigest()[:20]
        if any(p.stem == id_ for p in (raiz / 'livros').glob('*/video/avatares/*')):
            raise ValueError(f'o avatar de {nome} já pertence a outro livro; envie uma imagem própria')
    dados = {'titulo': titulo, 'provedor': provedor, 'idioma': 'pt', 'personagens': nomes,
             'apelidos': {}, 'vozes': {provedor: {n: fichas[n]['voz'].strip() for n in nomes}}}
    texto = yaml.safe_dump(dados, allow_unicode=True, sort_keys=False)
    cache = raiz / '.cache' / 'importacoes-video'
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as temporario:
        lv = ler_livro(texto, slug, Path(temporario))
        lv.dir_roteiro.mkdir(parents=True)
        (lv.dir / 'livro.yaml').write_text(texto, encoding='utf-8')
        (lv.dir_roteiro / 'cap_001.txt').write_text(previa['texto'], encoding='utf-8')
        separar_livro(lv)
        for nome in nomes:
            avatares.criar(lv, nome, [fichas[nome]['avatar']], nome=nome)
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            raise ValueError(f"já existe um livro '{slug}'; escolha outro título")
        lv.dir.rename(destino)
    return ler_livro(texto, slug, raiz)
