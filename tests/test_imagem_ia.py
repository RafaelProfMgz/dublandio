import base64
import json
from types import SimpleNamespace

import pytest

from dublandio import imagem_ia
from dublandio.imagem_ia import ErroIA

PNG = b'\x89PNG\r\n\x1a\nfoto'


class Resposta:
    def __init__(self, dados, status=200):
        self.dados, self.status_code, self.ok, self.text = dados, status, status < 400, json.dumps(dados)

    def json(self):
        return self.dados


@pytest.fixture
def openai(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-teste')
    chamadas = []

    def request(metodo, url, **kw):
        chamadas.append((url, kw))
        if url.endswith('chat/completions'):
            return Resposta({'choices': [{'message': {'content': ' rosto oval '}}]})
        return Resposta({'data': [{'b64_json': base64.b64encode(b'IMAGEM').decode()}]})
    monkeypatch.setattr(imagem_ia.requests, 'request', request)
    return chamadas


def test_sem_chave_avisa_antes_de_chamar(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with pytest.raises(ErroIA, match='OPENAI_API_KEY'):
        imagem_ia.criar_imagem({'nome': 'Ana'}, [], 'openai')


def test_openai_gera_sem_referencias(openai):
    png, pedido = imagem_ia.criar_imagem({'nome': 'Ana', 'idade': '30'}, [], 'openai')
    assert png == b'IMAGEM'
    assert 'Ana' in pedido and 'de frente' in pedido
    url, kw = openai[0]
    assert url.endswith('images/generations')
    assert kw['json']['prompt'] == pedido


def test_openai_com_referencias_usa_edicao(openai):
    imagem_ia.criar_imagem({'nome': 'Ana'}, [PNG, PNG], 'openai')
    url, kw = openai[0]
    assert url.endswith('images/edits')
    assert len(kw['files']) == 2


def test_descrever_com_openai_envia_as_fotos(openai):
    assert imagem_ia.descrever({'nome': 'Ana'}, [PNG], 'openai') == 'rosto oval'
    conteudo = openai[0][1]['json']['messages'][0]['content']
    assert conteudo[1]['image_url']['url'].startswith('data:image/png;base64,')


def test_descrever_sem_imagem_e_recusado(openai):
    with pytest.raises(ErroIA, match='ao menos uma'):
        imagem_ia.descrever({}, [], 'openai')


def test_chave_recusada_vira_erro_claro(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-ruim')
    monkeypatch.setattr(imagem_ia.requests, 'request', lambda *a, **k: Resposta({}, 401))
    with pytest.raises(ErroIA, match='recusou a chave'):
        imagem_ia.desenhar('x', [])


def test_claude_escreve_o_pedido_e_openai_desenha(openai, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-teste')
    enviados = {}

    class Mensagens:
        def create(self, **kw):
            enviados.update(kw)
            return SimpleNamespace(stop_reason='end_turn',
                                   content=[SimpleNamespace(type='text', text='Retrato de Ana, de frente.')])

    falso = SimpleNamespace(beta=SimpleNamespace(messages=Mensagens()))
    monkeypatch.setattr('anthropic.Anthropic', lambda **kw: falso)
    png, pedido = imagem_ia.criar_imagem({'nome': 'Ana'}, [PNG], 'claude')
    assert pedido == 'Retrato de Ana, de frente.'
    assert enviados['model'] == 'claude-opus-5-5'
    assert enviados['messages'][0]['content'][0]['type'] == 'image'
    assert openai[0][1]['data']['prompt'] == pedido  # a OpenAI desenhou com o pedido do Claude


def test_claude_recusa_vira_erro(openai, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-teste')
    resposta = SimpleNamespace(stop_reason='refusal', content=[])
    falso = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: resposta)))
    monkeypatch.setattr('anthropic.Anthropic', lambda **kw: falso)
    with pytest.raises(ErroIA, match='não quis'):
        imagem_ia.descrever({}, [PNG], 'claude')
