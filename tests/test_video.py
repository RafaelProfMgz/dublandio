import json
import subprocess
import wave
from unittest.mock import Mock

import pytest

from dublandio.audio import pcm_to_wav
from dublandio.cli import main
from dublandio.config import ler_livro
from dublandio.roteiro import parse_roteiro
from dublandio.sintetizar import chave_cache
from dublandio.video import ErroVideo, HeyGenVideo, gerar, juntar, planejar, recortar


@pytest.fixture
def pronto(livro):
    livro.avatares = {"Narrador": "avatar-n", "Fonoti": "avatar-f"}
    livro.video = {"segundos_por_trecho": 1}
    livro.dir_roteiro.mkdir(parents=True)
    texto = "Narrador: Uma leitura.\n\nEle: Outra leitura."
    (livro.dir_roteiro / "cap_001.txt").write_text(texto)
    pasta = livro.dir_cache / "cap_001"
    pasta.mkdir(parents=True)
    for i, fala in enumerate(parse_roteiro(texto, livro)):
        chave = chave_cache("heygen", fala.voz, livro.idioma, fala.texto)
        # 1,25 s por fala. Dados diferentes para detectar troca de ordem.
        (pasta / f"{chave}.wav").write_bytes(pcm_to_wav(bytes([i, 0]) * 10000, rate=8000))
    return livro


def test_config_video_e_avatares():
    lv = ler_livro('avatares: {Narrador: avatar-1}\nvideo: {formato: "9:16"}', "ex")
    assert lv.avatares == {"Narrador": "avatar-1"}
    assert lv.video["formato"] == "9:16"


def test_cortes_preservam_todas_as_amostras_e_ordem(pronto):
    trechos = planejar(pronto)
    assert [t.avatar for t in trechos] == ["avatar-n", "avatar-n", "avatar-f", "avatar-f"]
    assert [t.quadros for t in trechos] == [8000, 2000, 8000, 2000]
    for audio in {t.audio for t in trechos}:
        amostras = b""
        import io
        for t in trechos:
            if t.audio == audio:
                with wave.open(io.BytesIO(recortar(t))) as wav:
                    amostras += wav.readframes(wav.getnframes())
        with wave.open(audio) as original:
            assert amostras == original.readframes(original.getnframes())


def test_nao_usa_audio_de_roteiro_antigo(pronto):
    (pronto.dir_roteiro / "cap_001.txt").write_text("Narrador: Texto alterado.")
    with pytest.raises(ValueError, match="áudio não encontrado"):
        planejar(pronto)


def test_mudanca_de_avatar_invalida_cache(pronto):
    antes = planejar(pronto)
    pronto.avatares["Fonoti"] = "novo"
    depois = planejar(pronto)
    assert antes[0].chave == depois[0].chave
    assert antes[2].chave != depois[2].chave


@pytest.mark.parametrize("valor", [0, 121, True, "30", float("nan")])
def test_limites_invalidos(pronto, valor):
    pronto.video["segundos_por_trecho"] = valor
    with pytest.raises(ValueError, match="segundos_por_trecho"):
        planejar(pronto)


def test_cap_inexistente_nao_ignorado(pronto):
    with pytest.raises(ValueError, match="cap_002"):
        planejar(pronto, [1, 2])


def test_previa_sem_rede_sem_chave(pronto, monkeypatch, capsys):
    (pronto.dir / "livro.yaml").write_text("vozes:\n  heygen: {Narrador: N, Fonoti: X}\napelidos: {Ele: Fonoti}\n")
    monkeypatch.chdir(pronto.raiz)
    monkeypatch.setattr("requests.request", Mock(side_effect=AssertionError("não deve acessar a rede")))
    assert main(["videos", pronto.slug, "--cap", "1"]) == 0
    assert "Avatares pendentes: Fonoti, Narrador" in capsys.readouterr().out
    assert (pronto.dir / "video" / "plano.json").exists()


def test_valida_todos_avatares_antes_de_gastar(pronto):
    pronto.avatares.pop("Fonoti")
    cliente = Mock()
    with pytest.raises(ValueError, match="Fonoti"):
        gerar(pronto, planejar(pronto), cliente)
    cliente.enviar_audio.assert_not_called()


def test_retomada_preserva_id_apos_timeout(pronto, monkeypatch):
    monkeypatch.setattr("dublandio.video.shutil.which", lambda _: "/bin/ffmpeg")
    montagens = []
    monkeypatch.setattr("dublandio.video.juntar", lambda ts, ps, dest, formato: montagens.append(dest))
    cliente = Mock()
    cliente.enviar_audio.return_value = "asset-1"
    cliente.criar.return_value = "video-1"
    cliente.baixar.side_effect = ErroVideo("ainda processando")
    trechos = planejar(pronto)
    with pytest.raises(ErroVideo):
        gerar(pronto, trechos, cliente)
    assert montagens == []
    def baixar(identificador, destino):
        destino.write_bytes(b"mp4")
    cliente.baixar.side_effect = baixar
    gerar(pronto, trechos, cliente)
    # O primeiro ID foi retomado; os demais foram gerados uma única vez.
    assert cliente.criar.call_count == len(trechos)
    assert cliente.enviar_audio.call_count == len(trechos)
    payload = cliente.criar.call_args_list[0].args[0]
    assert payload["audio_asset_id"] == "asset-1"
    assert "script" not in payload and "voice_id" not in payload
    gerar(pronto, trechos, cliente)
    assert cliente.criar.call_count == len(trechos)


def test_post_incerto_fora_da_janela_nao_regera(pronto, monkeypatch):
    monkeypatch.setattr("dublandio.video.shutil.which", lambda _: "/bin/ffmpeg")
    trechos = planejar(pronto)
    pasta = pronto.dir_cache / "video"
    pasta.mkdir()
    (pasta / f"{trechos[0].chave}.json").write_text(json.dumps({"asset_id": "a", "solicitado_em": 1}))
    cliente = Mock()
    with pytest.raises(ErroVideo, match="23h"):
        gerar(pronto, trechos, cliente)
    cliente.criar.assert_not_called()


def test_cliente_payload_e_idempotencia(monkeypatch):
    request = Mock(return_value=Mock(status_code=200, json=lambda: {"data": {"video_id": "v"}}))
    monkeypatch.setattr("requests.request", request)
    cliente = HeyGenVideo("segredo")
    assert cliente.criar({"audio_asset_id": "a"}, "chave-estavel") == "v"
    assert request.call_args.kwargs["headers"]["Idempotency-Key"] == "chave-estavel"
    assert cliente.headers == {"X-Api-Key": "segredo"}


def test_cliente_falha_render_nao_baixa(monkeypatch, tmp_path):
    cliente = HeyGenVideo("k")
    monkeypatch.setattr(cliente, "_requisitar", lambda *a: {"status": "failed", "failure_message": "sem crédito"})
    with pytest.raises(ErroVideo, match="sem crédito"):
        cliente.baixar("v", tmp_path / "v.mp4", intervalo=0)
    assert not (tmp_path / "v.mp4").exists()


def test_montagem_usa_audio_original_codificado_uma_vez(pronto, monkeypatch):
    monkeypatch.setattr('dublandio.audio.executavel_ffmpeg', lambda: 'ffmpeg')
    trechos = planejar(pronto)
    comandos = []
    def executar(cmd, **kwargs):
        comandos.append(cmd)
        from pathlib import Path
        Path(cmd[-1]).touch()
    monkeypatch.setattr(subprocess, "run", executar)
    destino = pronto.dir / "video" / "cap_001.mp4"
    juntar(trechos, [pronto.dir / "clip.mp4"] * len(trechos), destino, "16:9")
    assert destino.exists()
    assert all("-an" in c for c in comandos[:len(trechos)])
    assert "aac" in comandos[-1] and "1:a:0" in comandos[-1]
    assert "trilha.wav" in comandos[-1][comandos[-1].index("-map") - 1]
