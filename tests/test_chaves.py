import pytest

from dublandio.chaves import Registro, situacao
from dublandio.tts import ErroConfig, ErroTTS, Verificacao


class Falso:
    nome = "heygen"

    def __init__(self, verificacao=Verificacao("ok"), erro: ErroTTS | None = None):
        self.verificacao = verificacao
        self.erro = erro

    def verificar(self):
        return self.verificacao

    def sintetizar(self, texto, voz, idioma):
        if self.erro:
            raise self.erro
        return b"RIFF"


@pytest.fixture(autouse=True)
def chave(monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "k1")


@pytest.fixture
def dia():
    return {"hoje": "2026-10-29"}


@pytest.fixture
def registro(tmp_path, dia):
    return Registro(tmp_path, hoje=lambda: dia["hoje"])


def sem_chave(nome):
    raise ErroConfig("sem chave")


def test_sem_chave_avisa_onde_colocar(registro):
    s = situacao("heygen", sem_chave, registro)
    assert s["situacao"] == "ausente" and s["bloqueia"]
    assert "Colocar chave" in s["mensagem"] and s["final"] is None


def test_chave_recusada_online(registro):
    s = situacao("heygen", lambda n: Falso(Verificacao("invalida", "HTTP 401")), registro)
    assert s["situacao"] == "invalida" and s["bloqueia"] and s["link_chave"]
    assert "recusou" in s["mensagem"]


def test_sem_conexao_nao_bloqueia(registro):
    s = situacao("heygen", lambda n: Falso(Verificacao("indisponivel", "timeout")), registro)
    assert s["situacao"] == "indisponivel" and not s["bloqueia"]


def test_cota_anotada_na_sintese_vale_ate_o_fim_do_dia(registro, dia):
    vigiado = registro.vigiar(Falso(erro=ErroTTS("used all", interromper=True, motivo="cota")))
    with pytest.raises(ErroTTS):
        vigiado.sintetizar("Oi", "v", "pt")
    s = situacao("heygen", lambda n: Falso(), registro)  # a conferência online não enxerga a cota
    assert s["situacao"] == "cota" and s["bloqueia"] and "amanhã" in s["mensagem"]
    dia["hoje"] = "2026-10-30"
    assert situacao("heygen", lambda n: Falso(), registro)["situacao"] == "ok"


def test_trocar_a_chave_esquece_o_erro(registro, monkeypatch):
    registro.anotar("heygen", "credito", "HTTP 402")
    assert situacao("heygen", lambda n: Falso(), registro)["situacao"] == "sem_credito"
    monkeypatch.setenv("HEYGEN_API_KEY", "k2")
    assert situacao("heygen", lambda n: Falso(), registro)["situacao"] == "ok"


def test_fala_que_passa_limpa_o_erro(registro):
    registro.anotar("heygen", "credito", "HTTP 402")
    registro.vigiar(Falso()).sintetizar("Oi", "v", "pt")
    assert registro.anotado("heygen") is None


def test_chave_aceita_online_desmente_recusa_anotada(registro):
    registro.anotar("heygen", "chave", "HTTP 401")
    assert situacao("heygen", lambda n: Falso(), registro)["situacao"] == "ok"
    assert registro.anotado("heygen") is None


def test_erro_comum_nao_e_anotado(registro):
    with pytest.raises(ErroTTS):
        registro.vigiar(Falso(erro=ErroTTS("HTTP 400"))).sintetizar("Oi", "v", "pt")
    assert registro.anotado("heygen") is None


def test_mensagem_usa_o_artigo_de_cada_provedor():
    from dublandio.chaves import mensagem

    assert "créditos do OpenRouter" in mensagem("openrouter", "sem_credito")
    assert mensagem("openrouter", "invalida").startswith("O OpenRouter recusou")
    assert mensagem("heygen", "invalida").startswith("A HeyGen recusou")
