from unittest.mock import MagicMock, patch

import pytest
import requests

from dublandio.tts import ErroConfig, ErroTTS, Voz, criar_provedor
from dublandio.tts.heygen import HeyGen
from dublandio.tts.openrouter import OpenRouter


def _resp(status=200, content=b"", headers=None, json_data=None):
    r = MagicMock(status_code=status, content=content, headers=headers or {}, text="erro")
    r.json.return_value = json_data or {}
    return r


def test_heygen_preserva_metadados_opcionais_de_voz():
    dados = {"data": {"voices": [{"voice_id": "v", "name": "Ana", "age": "young adult",
                                  "accent": "Brazilian", "description": "Calma e acolhedora"}]}}
    with patch("dublandio.tts.heygen.requests.get", return_value=_resp(json_data=dados)):
        voz = HeyGen("k").listar_vozes()[0]
    assert (voz.idade, voz.sotaque, voz.descricao) == ("young adult", "Brazilian", "Calma e acolhedora")


def test_openrouter_le_rate_do_content_type():
    resp = _resp(content=b"\x00\x00", headers={"Content-Type": "audio/pcm; rate=24000; channels=1"})
    with patch("dublandio.tts.openrouter.requests.post", return_value=resp) as post:
        wav = OpenRouter("k").sintetizar("Oi", "lucian", "pt")
    assert int.from_bytes(wav[24:28], "little") == 24000
    assert post.call_args.kwargs["json"]["voice"] == "lucian"


def test_heygen_baixa_audio_url():
    post = _resp(json_data={"data": {"audio_url": "https://x/a.wav"}})
    with patch("dublandio.tts.heygen.requests.post", return_value=post), \
         patch("dublandio.tts.heygen.requests.get", return_value=_resp(content=b"RIFFwav")) as get:
        assert HeyGen("k").sintetizar("Oi", "id", "pt") == b"RIFFwav"
    get.assert_called_once()


@pytest.mark.parametrize(("status", "retentavel"), [(429, True), (503, True), (400, False), (401, False)])
def test_status_http_define_retentavel(status, retentavel):
    with patch("dublandio.tts.openrouter.requests.post", return_value=_resp(status=status)):
        with pytest.raises(ErroTTS) as e:
            OpenRouter("k").sintetizar("Oi", "v", "pt")
    assert e.value.retentavel is retentavel


def test_timeout_e_retentavel():
    with patch("dublandio.tts.heygen.requests.post", side_effect=requests.Timeout("lento")):
        with pytest.raises(ErroTTS) as e:
            HeyGen("k").sintetizar("Oi", "v", "pt")
    assert e.value.retentavel


def test_chave_ausente_erro_config(monkeypatch):
    monkeypatch.delenv("HEYGEN_API_KEY", raising=False)
    with pytest.raises(ErroConfig, match="HEYGEN_API_KEY"):
        criar_provedor("heygen")


def test_heygen_lista_vozes():
    dados = {"data": {"voices": [
        {"voice_id": "v1", "name": "Yuri", "language": "Portuguese", "gender": "male", "preview_audio": "https://x/1.mp3"},
        {"voice_id": "v2", "name": None, "language": None, "gender": None, "preview_audio": ""},
        {"name": "sem id"},
    ]}}
    with patch("dublandio.tts.heygen.requests.get", return_value=_resp(json_data=dados)) as get:
        vozes = HeyGen("k").listar_vozes()
    assert get.call_args.kwargs["headers"] == {"X-Api-Key": "k"}
    assert vozes == [
        Voz("v1", "Yuri", "Portuguese", "male", "https://x/1.mp3"),
        Voz("v2", "v2", "", "", None),
    ]


def test_heygen_lista_vozes_erro_http():
    with patch("dublandio.tts.heygen.requests.get", return_value=_resp(status=401)):
        with pytest.raises(ErroTTS, match="401"):
            HeyGen("k").listar_vozes()


def test_heygen_cota_diaria_interrompe_sem_retentar():
    msg = {"error": {"code": "rate_limit_exceeded",
                     "message": "Your workspace has used all 200,000 free Turbo characters for today."}}
    resp = _resp(status=429, json_data={"message": str(msg)})
    with patch("dublandio.tts.heygen.requests.post", return_value=resp):
        with pytest.raises(ErroTTS, match="cota diária") as e:
            HeyGen("k").sintetizar("Oi", "v", "pt")
    assert e.value.interromper and not e.value.retentavel


def test_heygen_429_comum_so_retenta():
    resp = _resp(status=429, json_data={"message": "too many requests, slow down"})
    with patch("dublandio.tts.heygen.requests.post", return_value=resp):
        with pytest.raises(ErroTTS) as e:
            HeyGen("k").sintetizar("Oi", "v", "pt")
    assert e.value.retentavel and not e.value.interromper


@pytest.mark.parametrize(("status", "interromper"), [(401, True), (402, True), (403, True), (400, False), (500, False)])
def test_status_http_define_interromper(status, interromper):
    with patch("dublandio.tts.openrouter.requests.post", return_value=_resp(status=status)):
        with pytest.raises(ErroTTS) as e:
            OpenRouter("k").sintetizar("Oi", "v", "pt")
    assert e.value.interromper is interromper


@pytest.mark.parametrize(("status", "motivo"), [(401, "chave"), (403, "chave"), (402, "credito"), (400, None)])
def test_status_http_define_motivo(status, motivo):
    with patch("dublandio.tts.openrouter.requests.post", return_value=_resp(status=status)):
        with pytest.raises(ErroTTS) as e:
            OpenRouter("k").sintetizar("Oi", "v", "pt")
    assert e.value.motivo == motivo


def test_heygen_cota_diaria_tem_motivo_cota():
    resp = _resp(status=429, json_data={"message": "You have used all 200,000 free Turbo characters for today"})
    with patch("dublandio.tts.heygen.requests.post", return_value=resp):
        with pytest.raises(ErroTTS) as e:
            HeyGen("k").sintetizar("Oi", "v", "pt")
    assert e.value.motivo == "cota" and e.value.interromper


@pytest.mark.parametrize(("status", "situacao"), [(200, "ok"), (401, "invalida"), (500, "indisponivel")])
def test_heygen_verificar(status, situacao):
    with patch("dublandio.tts.heygen.requests.get", return_value=_resp(status=status)):
        assert HeyGen("k").verificar().situacao == situacao


def test_heygen_verificar_sem_internet():
    with patch("dublandio.tts.heygen.requests.get", side_effect=requests.ConnectionError("sem rede")):
        assert HeyGen("k").verificar().situacao == "indisponivel"


def _openrouter_verificar(chave, creditos=None):
    respostas = [chave] + ([creditos] if creditos else [])
    with patch("dublandio.tts.openrouter.requests.get", side_effect=respostas):
        return OpenRouter("k").verificar()


def test_openrouter_verificar_com_saldo():
    v = _openrouter_verificar(_resp(json_data={"data": {"limit_remaining": None}}),
                              _resp(json_data={"data": {"total_credits": 10, "total_usage": 2.5}}))
    assert (v.situacao, v.saldo) == ("ok", 7.5)


def test_openrouter_verificar_sem_saldo():
    v = _openrouter_verificar(_resp(json_data={"data": {}}),
                              _resp(json_data={"data": {"total_credits": 5, "total_usage": 5}}))
    assert v.situacao == "sem_credito"


def test_openrouter_verificar_limite_da_chave():
    assert _openrouter_verificar(_resp(json_data={"data": {"limit_remaining": 0}})).situacao == "sem_credito"


def test_openrouter_verificar_chave_recusada():
    assert _openrouter_verificar(_resp(status=401)).situacao == "invalida"


def test_openrouter_verificar_sem_saldo_visivel_aceita_a_chave():
    v = _openrouter_verificar(_resp(json_data={"data": {}}), _resp(status=403))
    assert (v.situacao, v.saldo) == ("ok", None)
