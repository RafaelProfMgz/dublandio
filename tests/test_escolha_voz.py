import pytest
import yaml

from dublandio.config import definir_voz


@pytest.mark.parametrize("texto", [
    'titulo: Ex\nvozes:\n  heygen:\n    Narrador: N # voz original\n  openrouter: {Narrador: reserva}\n',
    'titulo: Ex\nvozes: {heygen: {Narrador: N}, openrouter: {Narrador: reserva}}\n',
    'titulo: Ex\nvozes: {openrouter: {Narrador: reserva}}\n',
    'titulo: Ex\nvozes: null\n',
    'titulo: Ex\n',
])
def test_adicionar_voz_preserva_outros_dados_e_comentarios(texto):
    antes = yaml.safe_load(texto)
    novo = definir_voz(texto, 'heygen', 'Dra. Pell', 'voz: #especial')
    dados = yaml.safe_load(novo)
    assert dados['titulo'] == 'Ex'
    assert dados['vozes']['heygen']['Dra. Pell'] == 'voz: #especial'
    if (antes.get('vozes') or {}).get('openrouter'):
        assert dados['vozes']['openrouter'] == antes['vozes']['openrouter']
    if '# voz original' in texto:
        assert '# voz original' in novo
        assert dados['vozes']['heygen']['Narrador'] == 'N'


def test_alterar_voz_preserva_comentario_inline():
    texto = 'vozes:\n  heygen:\n    Narrador: antiga # preservar\n    Ana: outra\n'
    novo = definir_voz(texto, 'heygen', 'Narrador', 'nova')
    assert novo == texto.replace('antiga', '"nova"')

