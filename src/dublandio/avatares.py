"""Avatares dos personagens de um livro, para os vídeos.

Um avatar é uma ficha (nome, descrição, idade, voz) com uma ou mais imagens; a
imagem principal é a que o vídeo anima.

Regras:
- cada livro tem os seus avatares: uma imagem que já é de outro livro é recusada;
- cada personagem tem o seu avatar, e uma imagem pertence a um avatar só.

As imagens ficam em livros/<slug>/video/avatares/<hash>.png|jpg e as fichas em
livros/<slug>/video/avatares.json ({"avatares": [{id, personagem, nome, ...}]}).
"""

import hashlib
import json
import wave
from pathlib import Path

from dublandio.config import NARRADOR, Livro
from dublandio.roteiro import contar_personagens, ler_manifesto
from dublandio.sintetizar import gravar_mapa_de_falas, ler_mapa_de_falas, parte_em_cache

LIMITE_BYTES = 10_000_000
MAX_IMAGENS = 8
EXTENSOES = ('.png', '.jpg', '.jpeg')
CAMPOS = ('nome', 'descricao', 'idade', 'voz')


def pasta(livro: Livro) -> Path:
    return livro.dir / 'video' / 'avatares'


def _arquivo_fichas(livro: Livro) -> Path:
    return livro.dir / 'video' / 'avatares.json'


def _imagens(livro: Livro) -> dict[str, Path]:
    """nome do arquivo -> imagem guardada neste livro."""
    return {p.name: p for p in sorted(pasta(livro).glob('*')) if p.is_file() and p.suffix.lower() in EXTENSOES}


def _ficha(id_: str, personagem: str | None, imagens: list[str], **campos) -> dict:
    return {'id': id_, 'personagem': personagem, **{c: str(campos.get(c) or '') for c in CAMPOS},
            'imagens': imagens, 'principal': imagens[0]}


def _ler(livro: Livro) -> list[dict]:
    """Fichas do livro. Lê também o formato antigo ({"Personagem": "arquivo"}) e as imagens soltas."""
    path = _arquivo_fichas(livro)
    dados = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if not isinstance(dados, dict):
        raise ValueError(f'{path} precisa ser um mapa')
    if 'avatares' in dados:
        fichas = [dict(f) for f in dados['avatares']]
    else:  # formato antigo: uma imagem por personagem
        fichas = [_ficha(Path(arq).stem, str(p), [str(arq)], nome=p) for p, arq in dados.items()]
    existentes = _imagens(livro)
    for f in fichas:
        f['imagens'] = [i for i in f.get('imagens', []) if i in existentes]
        if f.get('principal') not in f['imagens']:
            f['principal'] = f['imagens'][0] if f['imagens'] else None
    fichas = [f for f in fichas if f['imagens']]
    usadas = {i for f in fichas for i in f['imagens']}
    fichas += [_ficha(Path(i).stem, None, [i], nome=i) for i in existentes if i not in usadas]
    return fichas


def _gravar(livro: Livro, fichas: list[dict]) -> None:
    path = _arquivo_fichas(livro)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporario = path.with_suffix('.tmp')
    temporario.write_text(json.dumps({'avatares': fichas}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporario.replace(path)


def personagens(livro: Livro) -> list[str]:
    """Personagens do livro: o Narrador, os que falam nos manifestos e os declarados no livro.yaml."""
    nomes = [NARRADOR] + [n for n, _ in contar_personagens(livro).most_common()]
    nomes += [livro.nome_canonico(p) for p in livro.personagens]
    return list(dict.fromkeys(nomes))


def personagens_do_capitulo(livro: Livro, cap: str) -> list[str]:
    """Quem fala no capítulo, na ordem em que aparece."""
    manifesto = livro.dir_manifesto / f'{cap}.json'
    if not manifesto.exists():
        return []
    return list(dict.fromkeys(f.personagem for f in ler_manifesto(manifesto)))


def listar(livro: Livro) -> list[dict]:
    imagens = _imagens(livro)
    return [{**f, 'caminho': imagens[f['principal']]} for f in _ler(livro)]


def mapa(livro: Livro) -> dict[str, Path]:
    """Personagem -> imagem principal do seu avatar."""
    imagens = _imagens(livro)
    return {f['personagem']: imagens[f['principal']] for f in _ler(livro) if f['personagem']}


def caminho(livro: Livro, identificador: str) -> Path | None:
    """Imagem principal do avatar."""
    f = next((f for f in _ler(livro) if f['id'] == identificador), None)
    return _imagens(livro)[f['principal']] if f else None


def imagem(livro: Livro, arquivo: str) -> Path | None:
    """Uma imagem qualquer do livro, pelo nome do arquivo (para as miniaturas)."""
    return _imagens(livro).get(arquivo)


def voz_do_personagem(livro: Livro, personagem: str) -> str:
    try:
        return livro.voz(personagem)
    except KeyError:
        return ''


def _validar_personagem(livro: Livro, personagem: str) -> str:
    nome = livro.nome_canonico(personagem.strip())
    if nome not in personagens(livro):
        raise ValueError(f'"{personagem}" não é personagem deste livro')
    return nome


def _livro_que_usa(livro: Livro, identificador: str) -> str | None:
    """Slug de outro livro que já tem esta imagem."""
    for outro in sorted((livro.raiz / 'livros').glob('*/video/avatares')):
        slug = outro.parent.parent.name
        if slug != livro.slug and any(p.stem == identificador for p in outro.glob('*')):
            return slug
    return None


def atribuir(livro: Livro, personagem: str, identificador: str) -> dict:
    """Dá a um personagem um avatar já guardado neste livro e ainda sem dono."""
    nome = _validar_personagem(livro, personagem)
    fichas = _ler(livro)
    alvo = next((f for f in fichas if f['id'] == identificador), None)
    if alvo is None:
        raise ValueError('avatar não encontrado neste livro')
    if alvo['personagem'] not in (None, nome):
        raise ValueError(f"esse avatar já é de {alvo['personagem']}; cada personagem precisa de um avatar próprio")
    for f in fichas:
        if f['personagem'] == nome and f is not alvo:
            f['personagem'] = None  # o avatar anterior fica livre
    alvo['personagem'] = nome
    _gravar(livro, fichas)
    return alvo


def _guardar_imagem(livro: Livro, dados: bytes) -> str:
    if not dados or len(dados) > LIMITE_BYTES:
        raise ValueError('envie imagens PNG ou JPEG de até 10 MB')
    if dados.startswith(b'\x89PNG\r\n\x1a\n'):
        ext = '.png'
    elif dados.startswith(b'\xff\xd8\xff'):
        ext = '.jpg'
    else:
        raise ValueError('envie imagens PNG ou JPEG')
    identificador = hashlib.sha256(dados).hexdigest()[:20]
    if outro := _livro_que_usa(livro, identificador):
        raise ValueError(f'uma das imagens já é avatar do livro "{outro}"; crie um avatar novo para este livro')
    destino = pasta(livro) / f'{identificador}{ext}'
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(dados)
    return destino.name


def criar(livro: Livro, personagem: str, imagens: list[bytes], principal: int = 0, **campos) -> dict:
    """Cria a ficha do avatar com as imagens enviadas e já a dá ao personagem.

    `campos`: nome, descricao, idade, voz (a voz padrão é a do personagem no livro).
    """
    nome = _validar_personagem(livro, personagem)
    if not imagens:
        raise ValueError('o avatar precisa de ao menos uma imagem')
    if len(imagens) > MAX_IMAGENS:
        raise ValueError(f'envie até {MAX_IMAGENS} imagens por avatar')
    if not 0 <= principal < len(imagens):
        raise ValueError('imagem principal inválida')
    fichas = _ler(livro)
    dono = {i: f for f in fichas for i in f['imagens']}
    arquivos = []
    for dados in imagens:
        arquivo = f'{hashlib.sha256(dados).hexdigest()[:20]}'
        ja = next((f for i, f in dono.items() if Path(i).stem == arquivo), None)
        if ja and ja['personagem'] not in (None, nome):
            raise ValueError(f"uma das imagens já é do avatar de {ja['personagem']}; "
                             'cada personagem precisa de um avatar próprio')
        arquivos.append(_guardar_imagem(livro, dados))
    arquivos = list(dict.fromkeys(arquivos))
    escolhida = _guardar_imagem(livro, imagens[principal])
    # Imagens que estavam em avatares sem dono passam para este.
    for f in fichas:
        f['imagens'] = [i for i in f['imagens'] if i not in arquivos]
    for f in fichas:
        if f['personagem'] == nome:
            f['personagem'] = None
    fichas = [f for f in fichas if f['imagens']]
    for f in fichas:
        if f['principal'] not in f['imagens']:
            f['principal'] = f['imagens'][0]
    campos = {c: (campos.get(c) or '').strip()[:2000] for c in CAMPOS}
    campos['nome'] = campos['nome'] or nome
    campos['voz'] = campos['voz'] or voz_do_personagem(livro, nome)
    nova = _ficha(Path(escolhida).stem, nome, arquivos, **campos)
    nova['principal'] = escolhida
    if any(f['id'] == nova['id'] for f in fichas):
        nova['id'] = hashlib.sha256('|'.join(arquivos).encode()).hexdigest()[:20]
    fichas.append(nova)
    _gravar(livro, fichas)
    return nova


def _juntar_seguidas(falas: list[tuple[str, int, int]]) -> list[tuple[str, int, int]]:
    resultado: list[list] = []
    for personagem, inicio, quadros in falas:
        if resultado and resultado[-1][0] == personagem:
            resultado[-1][2] += quadros
        else:
            resultado.append([personagem, inicio, quadros])
    return [tuple(s) for s in resultado]


def segmentos(livro: Livro, cap: str) -> list[tuple[str, int, int]]:
    """(personagem, início, quadros) no WAV do capítulo, juntando falas seguidas do mesmo personagem.

    Vem do mapa de falas que a síntese grava ao lado do WAV. Sem ele (áudio de antes do
    mapa), monta a partir das falas em cache, que formam o WAV sem pausas, e grava o mapa.
    """
    manifesto = livro.dir_manifesto / f'{cap}.json'
    audio = livro.dir_audio / f'{cap}.wav'
    if not audio.exists():
        raise ValueError(f'{cap}: falta o áudio do capítulo')
    if (salvo := ler_mapa_de_falas(audio)) is not None:
        return _juntar_seguidas(salvo)
    if not manifesto.exists():
        raise ValueError(f'{cap}: falta o manifesto do capítulo')
    try:
        with wave.open(str(audio)):
            pass
    except (wave.Error, EOFError) as e:
        raise ValueError(f'{cap}: o áudio do capítulo não é um WAV PCM legível') from e
    falas = []
    for fala in ler_manifesto(manifesto):
        parte = parte_em_cache(livro, cap, fala)
        if parte is None:
            raise ValueError(f'{cap}: este áudio não tem o mapa de quem fala quando. '
                             'Gere o áudio do capítulo de novo para criar o mapa.')
        falas.append((fala.personagem, parte))
    if not falas:
        raise ValueError(f'{cap}: capítulo sem falas')
    if gravar_mapa_de_falas(audio, falas) is None or (salvo := ler_mapa_de_falas(audio)) is None:
        raise ValueError(f'{cap}: o áudio do capítulo não corresponde às falas em cache '
                         '(roteiro ou vozes mudaram depois da síntese). Gere o áudio do capítulo de novo.')
    return _juntar_seguidas(salvo)
