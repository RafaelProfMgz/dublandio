import json
from pathlib import Path

import pytest

from dublandio.sintetizar import Cadeia, cadeia_do_livro, chave_cache, sintetizar_capitulo, sintetizar_livro
from dublandio.tts.base import ErroConfig, ErroTTS


class ProvedorFake:
    nome = "heygen"  # o provedor do livro de teste (conftest)

    def __init__(self, erros: list[ErroTTS] | None = None):
        self.chamadas: list[str] = []
        self._erros = list(erros or [])

    def sintetizar(self, texto, voz, idioma):
        self.chamadas.append(texto)
        if self._erros:
            raise self._erros.pop(0)
        return b"RIFF" + texto.encode()


class JuntarFake:
    def __init__(self):
        self.chamadas: list[tuple[list[Path], Path]] = []

    def __call__(self, partes, destino):
        self.chamadas.append((partes, destino))


def _manifesto(livro, cap, textos):
    livro.dir_manifesto.mkdir(parents=True, exist_ok=True)
    path = livro.dir_manifesto / f"{cap}.json"
    falas = [{"ordem": i, "personagem": "Narrador", "voz": "N", "texto": t} for i, t in enumerate(textos, 1)]
    path.write_text(json.dumps(falas), encoding="utf-8")
    return path


def test_gera_e_junta_no_audio_do_livro(livro):
    m = _manifesto(livro, "cap_001", ["Um.", "Dois."])
    juntar = JuntarFake()
    r = sintetizar_capitulo(livro, m, ProvedorFake(), juntar=juntar)
    assert (r.geradas, r.reusadas, r.falhas) == (2, 0, [])
    assert r.arquivo == livro.dir / "audio" / "cap_001.wav"
    assert len(juntar.chamadas[0][0]) == 2


def test_cache_hit_nao_chama_provedor(livro):
    m = _manifesto(livro, "cap_001", ["Um."])
    sintetizar_capitulo(livro, m, ProvedorFake(), juntar=JuntarFake())
    prov = ProvedorFake()
    r = sintetizar_capitulo(livro, m, prov, juntar=JuntarFake())
    assert prov.chamadas == [] and r.reusadas == 1


def test_texto_alterado_muda_chave():
    assert chave_cache("p", "v", "pt", "Um.") != chave_cache("p", "v", "pt", "Um!")
    assert chave_cache("p", "v", "pt", "Um.") != chave_cache("p", "w", "pt", "Um.")


def test_falha_nao_junta(livro):
    m = _manifesto(livro, "cap_001", ["Um.", "Dois."])
    juntar = JuntarFake()
    r = sintetizar_capitulo(livro, m, ProvedorFake([ErroTTS("HTTP 400", retentavel=False)]), juntar=juntar)
    assert len(r.falhas) == 1 and r.falhas[0][0].texto == "Um."
    assert r.geradas == 1 and r.arquivo is None and juntar.chamadas == []


def test_retenta_retentavel(livro):
    m = _manifesto(livro, "cap_001", ["Um."])
    prov = ProvedorFake([ErroTTS("429", retentavel=True), ErroTTS("503", retentavel=True)])
    r = sintetizar_capitulo(livro, m, prov, espera=0, juntar=JuntarFake())
    assert len(prov.chamadas) == 3 and r.geradas == 1 and not r.falhas


def test_desiste_apos_tentativas(livro):
    m = _manifesto(livro, "cap_001", ["Um."])
    prov = ProvedorFake([ErroTTS("429", retentavel=True)] * 5)
    r = sintetizar_capitulo(livro, m, prov, tentativas=3, espera=0, juntar=JuntarFake())
    assert len(prov.chamadas) == 3 and len(r.falhas) == 1


def test_nao_retenta_erro_fatal(livro):
    m = _manifesto(livro, "cap_001", ["Um."])
    prov = ProvedorFake([ErroTTS("401", retentavel=False)])
    sintetizar_capitulo(livro, m, prov, espera=0, juntar=JuntarFake())
    assert len(prov.chamadas) == 1


def test_filtra_capitulos(livro):
    _manifesto(livro, "cap_001", ["Um."])
    _manifesto(livro, "cap_002", ["Dois."])
    rs = sintetizar_livro(livro, ProvedorFake(), caps=[2], juntar=JuntarFake())
    assert [r.cap for r in rs] == ["cap_002"]


class Esgotado(ProvedorFake):
    """Sintetiza `limite` falas e depois responde como cota esgotada."""

    def __init__(self, nome, limite=0):
        super().__init__()
        self.nome, self.limite = nome, limite
        self.vozes: list[str] = []

    def sintetizar(self, texto, voz, idioma):
        self.chamadas.append(texto)
        if len(self.chamadas) > self.limite:
            raise ErroTTS("cota diária acabou", interromper=True)
        self.vozes.append(voz)
        return b"RIFF" + texto.encode()


def test_sem_reserva_cota_esgotada_para_sem_retentar(livro):
    m = _manifesto(livro, "cap_001", ["Um.", "Dois.", "Três."])
    prov, estados = Esgotado("heygen"), []
    with pytest.raises(ErroTTS, match="cota"):
        sintetizar_capitulo(livro, m, prov, espera=0, juntar=JuntarFake(),
                            ao_progredir=lambda fala, estado: estados.append(estado))
    assert prov.chamadas == ["Um."]  # nem retentou, nem passou para a fala seguinte
    assert estados == ["falhou: cota diária acabou"]


def test_cota_esgotada_troca_para_reserva_com_a_voz_dela(livro):
    livro.reserva = "openrouter"
    m1 = _manifesto(livro, "cap_001", ["Um.", "Dois."])
    m2 = _manifesto(livro, "cap_002", ["Três."])
    principal, reserva, trocas = Esgotado("heygen", limite=1), Esgotado("openrouter", limite=99), []
    juntar = JuntarFake()
    r1, r2 = sintetizar_livro(livro, Cadeia([principal, reserva]), espera=0, juntar=juntar,
                              ao_trocar=lambda de, para, motivo: trocas.append((de, para)))

    assert principal.vozes == ["N"] and reserva.vozes == ["lucian", "lucian"]  # vozes de cada provedor
    assert principal.chamadas == ["Um.", "Dois."]  # depois da troca, o principal não é chamado de novo
    assert trocas == [("heygen", "openrouter")]
    assert (r1.geradas, r2.geradas) == (2, 1) and r1.arquivo and r2.arquivo
    assert len(juntar.chamadas[0][0]) == 2

    # Rodar de novo reaproveita o que cada provedor gerou, sem chamar ninguém.
    novo = ProvedorFake()
    assert [r.reusadas for r in sintetizar_livro(livro, novo, juntar=JuntarFake())] == [2, 1]
    assert novo.chamadas == []


def test_reserva_sem_voz_para_tudo(livro):
    livro.reserva = "openrouter"
    livro.vozes["openrouter"] = {}
    m = _manifesto(livro, "cap_001", ["Um."])
    with pytest.raises(ErroTTS, match="não define voz"):
        sintetizar_capitulo(livro, m, Cadeia([Esgotado("heygen"), Esgotado("openrouter", 9)]), espera=0, juntar=JuntarFake())


def test_cadeia_do_livro_pula_provedor_sem_chave(livro):
    livro.reserva = "openrouter"

    def fabrica(nome):
        if nome == "heygen":
            raise ErroConfig("defina HEYGEN_API_KEY")
        return Esgotado(nome, 9)

    cadeia, avisos = cadeia_do_livro(livro, fabrica)
    assert cadeia.atual.nome == "openrouter" and not cadeia.trocar()
    assert avisos == ["heygen fora da síntese: defina HEYGEN_API_KEY"]

    def nenhuma(nome):
        raise ErroConfig(f"sem chave {nome}")

    with pytest.raises(ErroConfig, match="sem chave heygen; .*sem chave openrouter"):
        cadeia_do_livro(livro, nenhuma)


def test_sintese_grava_mapa_de_falas_para_o_video(livro):
    from dublandio.audio import pcm_to_wav

    livro.dir_manifesto.mkdir(parents=True, exist_ok=True)
    m = livro.dir_manifesto / "cap_001.json"
    m.write_text(json.dumps([{"ordem": 1, "personagem": "Narrador", "voz": "N", "texto": "aaaa"},
                             {"ordem": 2, "personagem": "Fonoti", "voz": "X", "texto": "bb"}]), encoding="utf-8")

    class Wav(ProvedorFake):
        def sintetizar(self, texto, voz, idioma):
            return pcm_to_wav(b"\0\0" * 10 * len(texto), rate=8000)

    def juntar(partes, destino):
        pcm = b"".join(p.read_bytes()[44:] for p in partes)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(pcm_to_wav(pcm, rate=8000))

    r = sintetizar_capitulo(livro, m, Wav(), juntar=juntar)
    mapa = json.loads((livro.dir_audio / "cap_001.falas.json").read_text())
    assert mapa["segmentos"] == [["Narrador", 0, 40], ["Fonoti", 40, 20]]
    assert mapa["total"] == 60
    assert r.arquivo.exists()


def test_audio_ilegivel_nao_grava_mapa(livro):
    m = _manifesto(livro, "cap_001", ["Um."])
    livro.dir_audio.mkdir(parents=True)
    velho = livro.dir_audio / "cap_001.falas.json"
    velho.write_text("{}")

    def juntar(partes, destino):
        destino.write_bytes(b"nao e wav")

    sintetizar_capitulo(livro, m, ProvedorFake(), juntar=juntar)
    assert not velho.exists()  # o mapa antigo não pode valer para o áudio novo
