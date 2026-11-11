import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from dublandio.audio import pcm_to_wav
from dublandio.cli import main
from dublandio.video import ErroVideo
from dublandio.video_hf import gerar_video_hf, montar_com_audio_original


@pytest.fixture
def entradas(tmp_path, monkeypatch):
    imagem, audio, destino = (tmp_path / n for n in ('avatar.png', 'audio.wav', 'video/final.mp4'))
    imagem.write_bytes(b'imagem')
    audio.write_bytes(pcm_to_wav(b'\0\0' * 8000, rate=8000))
    monkeypatch.setattr('dublandio.video_hf.shutil.which', lambda _: '/bin/ffmpeg')
    return imagem, audio, destino


def test_sem_token_nao_chama_demo(entradas, monkeypatch):
    cliente = Mock()
    monkeypatch.setattr('gradio_client.Client', cliente)
    with pytest.raises(ValueError, match='HF_TOKEN'):
        gerar_video_hf(*entradas, token='')
    cliente.assert_not_called()


def test_reusa_render_e_video_sem_repetir_chamada(entradas, monkeypatch):
    imagem, audio, destino = entradas
    render = imagem.parent / 'render.mp4'
    render.write_bytes(b'video')
    job = Mock()
    job.done.return_value = True
    job.result.return_value = {'video': str(render), 'subtitles': None}
    cliente = Mock()
    cliente.return_value.submit.return_value = job
    monkeypatch.setattr('gradio_client.Client', cliente)
    monkeypatch.setattr('gradio_client.handle_file', lambda path: path)
    montar = Mock(side_effect=lambda r, a, d: d.write_bytes(b'final'))
    monkeypatch.setattr('dublandio.video_hf.montar_com_audio_original', montar)
    assert gerar_video_hf(*entradas, token='segredo') == destino
    argumentos = cliente.return_value.submit.call_args
    assert argumentos.args[:2] == (str(imagem.resolve()), str(audio.resolve()))
    assert argumentos.args[2:] == ('full', True, 0, 1.0)
    assert argumentos.kwargs == {'api_name': '/generate'}
    assert gerar_video_hf(*entradas, token='segredo') == destino
    assert cliente.call_count == 1
    destino.unlink()
    gerar_video_hf(*entradas, token='segredo')
    assert cliente.call_count == 1  # falha de montagem não desperdiça outra cota
    assert montar.call_count == 2
    estado = json.loads(next(destino.parent.glob('.hf-cache/*/estado.json')).read_text())
    assert 'segredo' not in json.dumps(estado)


def test_erro_da_demo_nao_repete_e_oculta_token(entradas, monkeypatch):
    cliente = Mock(side_effect=RuntimeError('quota excedida segredo'))
    monkeypatch.setattr('gradio_client.Client', cliente)
    with pytest.raises(ErroVideo, match='quota excedida') as erro:
        gerar_video_hf(*entradas, token='segredo')
    assert 'segredo' not in str(erro.value)
    assert cliente.call_count == 1
    assert not entradas[2].exists()


def test_destino_existente_diferente_preservado(entradas):
    entradas[2].parent.mkdir()
    entradas[2].write_bytes(b'anterior')
    with pytest.raises(ValueError, match='destino já existe'):
        gerar_video_hf(*entradas, token='token')
    assert entradas[2].read_bytes() == b'anterior'


def test_montagem_troca_trilha_mas_preserva_imagem(entradas, monkeypatch):
    comandos = []
    def executar(cmd, **kwargs):
        comandos.append(cmd)
        Path(cmd[-1]).touch()
    monkeypatch.setattr('dublandio.video_hf.subprocess.run', executar)
    montar_com_audio_original(entradas[0], entradas[1], entradas[2])
    cmd = comandos[0]
    assert cmd[cmd.index('-c:v') + 1] == 'copy'
    assert '1:a:0' in cmd and str(entradas[1]) in cmd
    assert entradas[2].exists()


def test_cli_video_hf_repassa_arquivos(tmp_path, monkeypatch):
    pasta = tmp_path / 'livros/ex'
    pasta.mkdir(parents=True)
    (pasta / 'livro.yaml').write_text('titulo: Ex\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('HF_TOKEN', 'token')
    gerar = Mock(return_value=Path('video.mp4'))
    monkeypatch.setattr('dublandio.video_hf.gerar_video_hf', gerar)
    assert main(['video-hf', 'ex', '--avatar', 'a.png', '--audio', 'a.wav', '--nome', 'teste']) == 0
    assert gerar.call_args.args == (Path('a.png'), Path('a.wav'), Path('livros/ex/video/teste.mp4'), 'token')
    assert main(['video-hf', 'ex', '--avatar', 'a.png', '--audio', 'a.wav', '--nome', '../fora']) == 2
