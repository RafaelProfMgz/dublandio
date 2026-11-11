import json

import pytest

from dublandio import avatares
from dublandio.config import Livro

PNG = b'\x89PNG\r\n\x1a\n'


def png(conteudo: str) -> bytes:
    return PNG + conteudo.encode()


@pytest.fixture
def outro(livro):
    return Livro(slug='outro', titulo='Outro', origem=None, provedor='heygen',
                 personagens=['Kamille'], vozes={'heygen': {'Narrador': 'N'}}, raiz=livro.raiz)


def test_criar_guarda_ficha_e_varias_imagens(livro):
    a = avatares.criar(livro, 'Fa', [png('1'), png('2')], principal=1,
                       nome='Fa', descricao='cabelo curto', idade='30')
    assert a['personagem'] == 'Fa Yuiry'  # apelido vira nome canônico
    assert (a['nome'], a['descricao'], a['idade']) == ('Fa', 'cabelo curto', '30')
    assert a['voz'] == 'F'  # a voz do personagem no livro
    assert len(a['imagens']) == 2
    assert a['principal'] == a['imagens'][1]
    assert avatares.mapa(livro)['Fa Yuiry'].name == a['principal']
    assert avatares.caminho(livro, a['id']).name == a['principal']


def test_nome_padrao_e_o_do_personagem(livro):
    assert avatares.criar(livro, 'Kamille', [png('k')])['nome'] == 'Kamille'


def test_personagem_desconhecido_e_recusado(livro):
    with pytest.raises(ValueError, match='não é personagem'):
        avatares.criar(livro, 'Ninguém', [png('x')])


def test_sem_imagem_ou_formato_invalido(livro):
    with pytest.raises(ValueError, match='ao menos uma'):
        avatares.criar(livro, 'Kamille', [])
    with pytest.raises(ValueError, match='PNG ou JPEG'):
        avatares.criar(livro, 'Kamille', [b'GIF89a'])


def test_uma_imagem_nao_serve_a_dois_personagens(livro):
    a = avatares.criar(livro, 'Kamille', [png('k')])
    with pytest.raises(ValueError, match='Kamille'):
        avatares.criar(livro, 'Narrador', [png('k')])
    with pytest.raises(ValueError, match='já é de Kamille'):
        avatares.atribuir(livro, 'Narrador', a['id'])


def test_imagem_de_outro_livro_e_recusada(livro, outro):
    avatares.criar(outro, 'Kamille', [png('k')])
    with pytest.raises(ValueError, match='outro'):
        avatares.criar(livro, 'Kamille', [png('k')])
    assert avatares.mapa(livro) == {}


def test_trocar_avatar_libera_o_antigo(livro):
    antigo = avatares.criar(livro, 'Kamille', [png('1')])
    avatares.criar(livro, 'Kamille', [png('2')])
    livres = [a for a in avatares.listar(livro) if a['personagem'] is None]
    assert [a['id'] for a in livres] == [antigo['id']]
    assert avatares.atribuir(livro, 'Narrador', antigo['id'])['personagem'] == 'Narrador'
    assert len(avatares.mapa(livro)) == 2


def test_le_formato_antigo_e_imagens_soltas(livro):
    pasta = avatares.pasta(livro)
    pasta.mkdir(parents=True)
    (pasta / 'aaa.png').write_bytes(png('a'))
    (pasta / 'bbb.png').write_bytes(png('b'))
    (livro.dir / 'video' / 'avatares.json').write_text(json.dumps({'Kamille': 'aaa.png'}))
    fichas = {a['id']: a for a in avatares.listar(livro)}
    assert fichas['aaa']['personagem'] == 'Kamille'
    assert fichas['bbb']['personagem'] is None
    # Uma imagem solta pode entrar num avatar novo.
    novo = avatares.criar(livro, 'Narrador', [png('b')])
    assert novo['personagem'] == 'Narrador'


def test_atribuir_avatar_inexistente(livro):
    with pytest.raises(ValueError, match='não encontrado'):
        avatares.atribuir(livro, 'Kamille', 'nada')
