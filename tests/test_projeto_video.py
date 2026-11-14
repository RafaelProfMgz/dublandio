import asyncio
import base64

import httpx
import pytest

from dublandio import avatares
from dublandio.audio import pcm_to_wav
from dublandio.cli import main
from dublandio.config import carregar_livro
from dublandio.gui.servidor import criar_app
from dublandio.projeto_video import analisar_roteiro, criar_projeto
from dublandio.roteiro import ler_manifesto


ROTEIRO = 'Narrador: A porta abriu.\nAna: Olá!\nNarrador: Ela sorriu.'


def fichas():
    return [{'nome': n, 'voz': v, 'avatar': b'\x89PNG\r\n\x1a\n' + n.encode()}
            for n, v in [('Narrador', 'N'), ('Ana', 'A')]]


def test_analise_reconhece_falas_por_linha_e_narracao():
    p = analisar_roteiro('A porta abriu.\r\n\r\nAna: Olá!\r\nBruno: Oi!')
    assert p['total_falas'] == 3
    assert p['personagens'] == [{'nome': n, 'falas': 1} for n in ['Narrador', 'Ana', 'Bruno']]
    assert analisar_roteiro(p['texto']) == p


def test_cria_projeto_completo_sem_audio_ou_origem(tmp_path):
    lv = criar_projeto(tmp_path, 'Meu vídeo', ROTEIRO, fichas())
    assert lv.origem is None
    assert not lv.dir_audio.exists()
    assert set(avatares.mapa(lv)) == {'Narrador', 'Ana'}
    falas = ler_manifesto(lv.dir_manifesto / 'cap_001.json')
    assert [(f.personagem, f.voz) for f in falas] == [('Narrador', 'N'), ('Ana', 'A'), ('Narrador', 'N')]
    assert carregar_livro(lv.slug, tmp_path).vozes == lv.vozes


@pytest.mark.parametrize('problema', ['sem_avatar', 'avatar_repetido', 'imagem_invalida', 'sem_voz', 'sem_personagem', 'repetido'])
def test_importacao_invalida_nao_deixa_livro_parcial(tmp_path, problema):
    ps = fichas()
    if problema == 'sem_avatar':
        ps[1]['avatar'] = b''
    elif problema == 'avatar_repetido':
        ps[1]['avatar'] = ps[0]['avatar']
    elif problema == 'imagem_invalida':
        ps[1]['avatar'] = b'nao e foto'
    elif problema == 'sem_voz':
        ps[1]['voz'] = ' '
    elif problema == 'sem_personagem':
        ps.pop()
    else:
        ps.append(ps[0])
    with pytest.raises(ValueError):
        criar_projeto(tmp_path, 'Inválido', ROTEIRO, ps)
    assert not (tmp_path / 'livros' / 'invalido').exists()


def test_nao_reutiliza_avatar_de_outro_livro_ou_sobrescreve(tmp_path):
    lv = criar_projeto(tmp_path, 'Original', ROTEIRO, fichas())
    with pytest.raises(ValueError, match='já existe'):
        criar_projeto(tmp_path, 'Original', ROTEIRO, fichas())
    with pytest.raises(ValueError, match='outro livro'):
        criar_projeto(tmp_path, 'Cópia', ROTEIRO, fichas())
    assert set(avatares.mapa(lv)) == {'Narrador', 'Ana'}


@pytest.mark.parametrize('texto', ['', '  \n  '])
def test_roteiro_vazio_e_recusado(texto):
    with pytest.raises(ValueError, match='pelo menos uma fala'):
        analisar_roteiro(texto)


def test_cli_resolve_fotos_relativas_ao_yaml(tmp_path, monkeypatch):
    origem = tmp_path / 'entradas'
    origem.mkdir()
    for p in fichas():
        (origem / f"{p['nome']}.png").write_bytes(p['avatar'])
    (origem / 'elenco.yaml').write_text('Narrador: {voz: N, avatar: Narrador.png}\nAna: {voz: A, avatar: Ana.png}', encoding='utf-8')
    (origem / 'roteiro.txt').write_text(ROTEIRO, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    assert main(['novo-video', str(origem / 'roteiro.txt'), '--titulo', 'CLI',
                 '--personagens', str(origem / 'elenco.yaml')]) == 0
    assert set(avatares.mapa(carregar_livro('cli'))) == {'Narrador', 'Ana'}


def requisitar(app, metodo, url, **kwargs):
    async def executar():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://teste') as c:
            return await c.request(metodo, url, **kwargs)
    return asyncio.run(executar())


def test_api_importa_e_recusa_base64_invalido(tmp_path):
    app = criar_app(tmp_path)
    previa = requisitar(app, 'POST', '/api/video/roteiro', json={'texto': ROTEIRO})
    assert previa.status_code == 200 and previa.json()['total_falas'] == 3
    pedido = {'titulo': 'API', 'texto': ROTEIRO,
              'personagens': [{**p, 'avatar': base64.b64encode(p['avatar']).decode()} for p in fichas()]}
    r = requisitar(app, 'POST', '/api/video/projetos', json=pedido)
    assert r.status_code == 200 and r.json()['slug'] == 'api'
    pedido['titulo'] = 'Inválido'
    pedido['personagens'][0]['avatar'] = '***'
    assert requisitar(app, 'POST', '/api/video/projetos', json=pedido).status_code == 400
    assert not (tmp_path / 'livros' / 'invalido').exists()


def test_geracao_sintetiza_antes_de_animar_e_exige_opt_in(tmp_path, monkeypatch):
    lv = criar_projeto(tmp_path, 'Vídeo', ROTEIRO, fichas())
    etapas = []

    class Provedor:
        nome = 'heygen'

        def sintetizar(self, texto, voz, idioma):
            etapas.append(('voz', voz))
            return pcm_to_wav(b'\x00\x00' * 100)

    def juntar(partes, destino):
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(pcm_to_wav(b'\x00\x00' * (100 * len(partes))))

    def animar(*args, **kwargs):
        assert lv.dir_audio.joinpath('cap_001.wav').exists()
        assert lv.dir_audio.joinpath('cap_001.falas.json').exists()
        etapas.append(('video', None))

    monkeypatch.setenv('HF_TOKEN', 'teste')
    monkeypatch.setattr('dublandio.gui.servidor.shutil.which', lambda _: 'ffmpeg')
    monkeypatch.setattr('dublandio.gui.servidor.executar_capitulo', animar)
    app = criar_app(tmp_path, fabrica_provedor=lambda _: Provedor(), juntar=juntar, espera=0)
    url = f'/api/livros/{lv.slug}/videos/tarefas'
    assert requisitar(app, 'POST', url, json={'cap': 'cap_001'}).status_code == 400
    assert not etapas
    r = requisitar(app, 'POST', url, json={'cap': 'cap_001', 'gerar_audio': True})
    assert r.status_code == 200
    app.state.tarefas.aguardar(5)
    eventos = list(app.state.tarefas.eventos(r.json()['desde'], espera=0))
    assert eventos[-1]['ok'], eventos
    assert etapas == [('voz', 'N'), ('voz', 'A'), ('voz', 'N'), ('video', None)]


def test_avatar_ausente_impede_sintese(tmp_path, monkeypatch):
    lv = criar_projeto(tmp_path, 'Vídeo', ROTEIRO, fichas())
    avatares.mapa(lv)['Ana'].unlink()
    monkeypatch.setenv('HF_TOKEN', 'teste')
    monkeypatch.setattr('dublandio.gui.servidor.shutil.which', lambda _: 'ffmpeg')

    def fabrica(_):
        pytest.fail('não deve iniciar a síntese antes de conferir os avatares')

    app = criar_app(tmp_path, fabrica_provedor=fabrica)
    r = requisitar(app, 'POST', f'/api/livros/{lv.slug}/videos/tarefas', json={'cap': 'cap_001', 'gerar_audio': True})
    assert r.status_code == 400 and 'Ana' in r.json()['detail']
