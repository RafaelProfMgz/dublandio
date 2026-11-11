import hashlib
import json
import wave
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dublandio import avatares

from dublandio.audio import pcm_to_wav
from dublandio.capitulo_hf import executar_capitulo, preparar_capitulo
from dublandio.cli import main
from dublandio.sintetizar import chave_cache
from dublandio.video import ErroVideo


def falas(livro, *partes):
    """Manifesto + cache de falas (personagem, pcm) e o WAV do capítulo, que é a junção delas."""
    livro.dir_manifesto.mkdir(parents=True, exist_ok=True)
    livro.dir_audio.mkdir(parents=True, exist_ok=True)
    cache = livro.dir_cache / 'cap_001'
    cache.mkdir(parents=True, exist_ok=True)
    manifesto = []
    for i, (personagem, pcm) in enumerate(partes, 1):
        texto = f'fala {i}'
        voz = livro.voz(personagem)
        manifesto.append({'ordem': i, 'personagem': personagem, 'voz': voz, 'texto': texto})
        (cache / f"{chave_cache('heygen', voz, 'pt', texto)}.wav").write_bytes(pcm_to_wav(pcm, rate=8000))
    (livro.dir_manifesto / 'cap_001.json').write_text(json.dumps(manifesto))
    (livro.dir_audio / 'cap_001.wav').write_bytes(pcm_to_wav(b''.join(p for _, p in partes), rate=8000))


@pytest.fixture
def cap(livro):
    falas(livro, ('Narrador', b'\1\0' * 48000))
    imagem = livro.dir / 'avatar.png'
    imagem.write_bytes(b'avatar')
    return livro, {'Narrador': imagem}


PNG = b'\x89PNG\r\n\x1a\n' + b'foto'


def cota(segundos):
    return SimpleNamespace(remaining=segundos, resets_at='amanhã')


def gerar(imagem, audio, destino, token, **kw):
    destino.write_bytes(b'video')


def montar(trechos, partes, destino, formato):
    assert all(p.is_file() for p in partes)
    destino.write_bytes(b'montado')


def test_previa_apenas_prepara_sem_rede(cap, monkeypatch):
    livro, _ = cap
    (livro.dir / 'livro.yaml').write_text('titulo: Exemplo\nvozes:\n  heygen: {Narrador: N}\n')
    foto = livro.raiz / 'foto.png'
    foto.write_bytes(PNG)
    monkeypatch.chdir(livro.raiz)
    rede = Mock(side_effect=AssertionError('sem rede'))
    monkeypatch.setattr('huggingface_hub.HfApi', rede)
    assert main(['capitulo-hf', livro.slug, '--cap', '1', '--avatar', f'Narrador={foto}']) == 0
    rede.assert_not_called()
    assert list(avatares.mapa(livro)) == ['Narrador']


def test_para_na_cota_e_retoma_sem_repetir_trechos(cap):
    livro, imagem = cap
    provedor = Mock(side_effect=gerar)
    quotas = Mock(side_effect=[cota(300), cota(95)])
    estado = executar_capitulo(livro, 1, 'token', imagem, consultar_cota=quotas, gerar=provedor, montar=montar)
    assert estado['situacao'] == 'aguardando_cota'
    assert len(estado['trechos']) == 1
    assert estado['trechos'][0]['quadros'] == 40000
    assert 'parcial' in estado['previa']
    assert not (livro.dir / 'video/cap_001-hf.mp4').exists()
    estado = executar_capitulo(livro, 1, 'token', imagem, consultar_cota=lambda: cota(300), gerar=provedor, montar=montar)
    assert estado['situacao'] == 'concluido'
    assert provedor.call_count == 2
    assert sum(t['quadros'] for t in estado['trechos']) == 48000
    assert [t['inicio'] for t in estado['trechos']] == [0, 40000]
    amostras = b''
    for t in estado['trechos']:
        with wave.open(t['audio']) as wav:
            amostras += wav.readframes(wav.getnframes())
    assert amostras == b'\1\0' * 48000
    consulta = Mock(side_effect=AssertionError('já terminou'))
    executar_capitulo(livro, 1, 'token', imagem, consultar_cota=consulta, gerar=provedor, montar=montar)
    consulta.assert_not_called()
    assert provedor.call_count == 2


def test_adapta_corte_a_cota_disponivel(cap):
    livro, imagem = cap
    estado = executar_capitulo(livro, 1, 'token', imagem,
                               consultar_cota=Mock(side_effect=[cota(200), cota(0)]), gerar=gerar, montar=montar)
    assert estado['trechos'][0]['quadros'] == 16000  # 2 s: reserva com o fator de admissão


def test_sem_cota_nao_envia_audio(cap):
    livro, imagem = cap
    provedor = Mock()
    estado = executar_capitulo(livro, 1, 'token', imagem, consultar_cota=lambda: cota(0), gerar=provedor, montar=montar)
    assert estado['situacao'] == 'aguardando_cota'
    assert estado['trechos'] == []
    provedor.assert_not_called()


def test_mudanca_no_audio_original_bloqueia_mistura(cap):
    livro, imagem = cap
    preparar_capitulo(livro, 1, imagem)
    (livro.dir_audio / 'cap_001.wav').write_bytes(pcm_to_wav(b'\2\0' * 96000, rate=8000))
    with pytest.raises(ValueError, match='mud'):
        preparar_capitulo(livro, 1, imagem)


def test_falha_preserva_pendente_e_nao_monta_final(cap):
    livro, imagem = cap
    provedor = Mock(side_effect=ErroVideo('demo offline'))
    montador = Mock()
    with pytest.raises(ErroVideo):
        executar_capitulo(livro, 1, 'token', imagem, consultar_cota=lambda: cota(300), gerar=provedor, montar=montador)
    estado, path = preparar_capitulo(livro, 1, imagem)
    assert estado['situacao'] == 'interrompido'
    assert not estado['trechos'][0]['concluido']
    assert not (path.parent / 'gerando.lock').exists()
    montador.assert_not_called()


def test_duas_execucoes_nao_disputam_cota(cap):
    livro, imagem = cap
    _, path = preparar_capitulo(livro, 1, imagem)
    (path.parent / 'gerando.lock').touch()
    with pytest.raises(ErroVideo, match='andamento'):
        executar_capitulo(livro, 1, 'token', imagem, consultar_cota=lambda: cota(300))


def test_pedido_recusado_por_duracao_e_recortado_sem_pular_audio(cap):
    livro, imagem = cap
    estado, path = preparar_capitulo(livro, 1, imagem)
    estado.update(ultimo_erro='The requested GPU duration (412s) is larger than the maximum allowed',
                  proximo_inicio=48000)
    estado['trechos'] = [{'inicio': 0, 'quadros': 48000, 'audio': str(path.parent / 'antigo.wav'),
                         'video': str(path.parent / 'antigo.mp4'), 'concluido': False}]
    path.write_text(json.dumps(estado))
    novo = executar_capitulo(livro, 1, 'token', imagem,
                              consultar_cota=Mock(side_effect=[cota(300), cota(0)]), gerar=gerar, montar=montar)
    assert novo['trechos'][0]['inicio'] == 0
    assert novo['trechos'][0]['quadros'] == 40000
    assert novo['proximo_inicio'] == 40000
    assert novo['situacao'] == 'aguardando_cota'


def test_limite_de_execucoes_para_sem_repetir_e_monta_previa(cap):
    livro, imagem = cap
    chamadas = []
    def provedor(imagem, audio, destino, token, **kw):
        chamadas.append(destino)
        if len(chamadas) == 2:
            raise ErroVideo('You have exceeded your ZeroGPU runs limit.')
        destino.write_bytes(b'video')
    estado = executar_capitulo(livro, 1, 'token', imagem, consultar_cota=lambda: cota(300), gerar=provedor, montar=montar)
    assert len(chamadas) == 2
    assert estado['situacao'] == 'aguardando_cota'
    assert 'runs limit' in estado['motivo_pausa']
    assert 'parcial' in estado['previa']
    assert estado['trechos'][0]['concluido']
    assert not estado['trechos'][1]['concluido']


def test_cada_personagem_usa_o_seu_avatar_e_cortes_nao_misturam(livro):
    falas(livro, ('Narrador', b'\1\0' * 12000), ('Fonoti', b'\2\0' * 20000), ('Narrador', b'\3\0' * 4000))
    fotos = {}
    for nome in ('Narrador', 'Fonoti'):
        fotos[nome] = livro.dir / f'{nome}.png'
        fotos[nome].write_bytes(nome.encode())
    usadas = []

    def provedor(imagem, audio, destino, token, **kw):
        usadas.append(imagem.name)
        destino.write_bytes(b'video')
    estado = executar_capitulo(livro, 1, 'token', fotos, consultar_cota=lambda: cota(300), gerar=provedor, montar=montar)
    assert estado['situacao'] == 'concluido'
    cortes = [(t['personagem'], t['inicio'], t['quadros']) for t in estado['trechos']]
    # 5 s = 40000 quadros, mas nenhum corte atravessa a troca de personagem.
    assert cortes == [('Narrador', 0, 12000), ('Fonoti', 12000, 20000), ('Narrador', 32000, 4000)]
    assert usadas == ['Narrador.png', 'Fonoti.png', 'Narrador.png']


def test_personagem_sem_avatar_bloqueia(livro):
    falas(livro, ('Narrador', b'\1\0' * 100), ('Fonoti', b'\1\0' * 100))
    foto = livro.dir / 'n.png'
    foto.write_bytes(b'n')
    with pytest.raises(ValueError, match='Fonoti'):
        preparar_capitulo(livro, 1, {'Narrador': foto})


def test_mesma_foto_para_dois_personagens_bloqueia(livro):
    falas(livro, ('Narrador', b'\1\0' * 100), ('Fonoti', b'\1\0' * 100))
    foto = livro.dir / 'n.png'
    foto.write_bytes(b'n')
    with pytest.raises(ValueError, match='próprio'):
        preparar_capitulo(livro, 1, {'Narrador': foto, 'Fonoti': foto})


def test_sem_cache_das_falas_nao_da_para_separar_personagens(cap):
    livro, imagem = cap
    for p in (livro.dir_cache / 'cap_001').iterdir():
        p.unlink()
    with pytest.raises(ValueError, match='mapa'):
        preparar_capitulo(livro, 1, imagem)


def test_progresso_antigo_de_avatar_unico_retoma(cap):
    livro, imagem = cap
    estado, path = preparar_capitulo(livro, 1, imagem)
    f = estado['fontes']
    antigo = livro.dir / 'narrador.png'
    antigo.write_bytes(b'antigo')
    f['avatar'], f['avatar_sha256'] = str(antigo), hashlib.sha256(b'antigo').hexdigest()
    del f['avatares'], f['segmentos']
    path.write_text(json.dumps(estado))
    usadas = []
    def provedor(imagem, audio, destino, token, **kw):
        usadas.append(imagem)
        destino.write_bytes(b'video')
    novo = executar_capitulo(livro, 1, 'token', consultar_cota=lambda: cota(300), gerar=provedor, montar=montar)
    assert novo['situacao'] == 'concluido'
    assert set(usadas) == {antigo}


def test_trocar_avatar_antes_de_gerar_vale_depois_nao(cap):
    livro, imagem = cap
    preparar_capitulo(livro, 1, imagem)
    outra = livro.dir / 'outra.png'
    outra.write_bytes(b'outra')
    estado, _ = preparar_capitulo(livro, 1, {'Narrador': outra})  # nada gerado ainda
    assert estado['fontes']['avatares']['Narrador']['caminho'] == str(outra.resolve())
    executar_capitulo(livro, 1, 'token', {'Narrador': outra},
                      consultar_cota=Mock(side_effect=[cota(300), cota(0)]), gerar=gerar, montar=montar)
    with pytest.raises(ValueError, match='mudou'):
        preparar_capitulo(livro, 1, imagem)


def test_mapa_de_falas_dispensa_o_cache(livro):
    falas(livro, ('Narrador', b'\1\0' * 100), ('Fonoti', b'\2\0' * 50))
    assert avatares.segmentos(livro, 'cap_001') == [('Narrador', 0, 100), ('Fonoti', 100, 50)]
    # O mapa foi gravado ao lado do WAV: apagar o cache não atrapalha mais o vídeo.
    assert (livro.dir_audio / 'cap_001.falas.json').exists()
    for p in (livro.dir_cache / 'cap_001').iterdir():
        p.unlink()
    assert avatares.segmentos(livro, 'cap_001') == [('Narrador', 0, 100), ('Fonoti', 100, 50)]


def test_mapa_de_falas_velho_nao_vale_para_audio_novo(livro):
    falas(livro, ('Narrador', b'\1\0' * 100))
    avatares.segmentos(livro, 'cap_001')
    for p in (livro.dir_cache / 'cap_001').iterdir():
        p.unlink()
    (livro.dir_audio / 'cap_001.wav').write_bytes(pcm_to_wav(b'\1\0' * 300, rate=8000))
    with pytest.raises(ValueError, match='mapa'):
        avatares.segmentos(livro, 'cap_001')
