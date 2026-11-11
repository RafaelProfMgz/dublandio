import pytest

from dublandio.catalogo import VALIDADE, carregar_catalogo, filtrar
from dublandio.tts import ErroConfig, Voz

VOZES = [
    Voz("b", "Yuri", "Portuguese", "male", "https://x/yuri.mp3"),
    Voz("a", "Ana - Calma", "Portuguese", "female", "https://x/ana.mp3"),
    Voz("c", "Leanne", "English", "female"),
    Voz("d", "Mix", "Multilingual", "male"),
]


class ComLista:
    nome = "heygen"

    def __init__(self):
        self.chamadas = 0

    def listar_vozes(self):
        self.chamadas += 1
        return list(VOZES)


def test_busca_ordena_e_guarda_em_cache(tmp_path):
    provedor = ComLista()
    vozes, _ = carregar_catalogo("heygen", lambda nome: provedor, tmp_path)
    assert [v.nome for v in vozes] == ["Leanne", "Mix", "Ana - Calma", "Yuri"]
    assert (tmp_path / ".cache" / "catalogo" / "heygen.json").exists()

    de_novo, _ = carregar_catalogo("heygen", lambda nome: provedor, tmp_path)
    assert de_novo == vozes and provedor.chamadas == 1


def test_cache_vencido_ou_atualizar_busca_de_novo(tmp_path):
    import time

    provedor = ComLista()
    carregar_catalogo("heygen", lambda nome: provedor, tmp_path)
    carregar_catalogo("heygen", lambda nome: provedor, tmp_path, agora=lambda: time.time() + VALIDADE + 1)
    carregar_catalogo("heygen", lambda nome: provedor, tmp_path, atualizar=True)
    assert provedor.chamadas == 3


def test_cache_valido_nao_precisa_de_chave(tmp_path):
    carregar_catalogo("heygen", lambda nome: ComLista(), tmp_path)

    def sem_chave(nome):
        raise ErroConfig("defina HEYGEN_API_KEY")

    vozes, _ = carregar_catalogo("heygen", sem_chave, tmp_path)
    assert len(vozes) == 4


def test_provedor_sem_lista(tmp_path):
    class SoSintetiza:
        nome = "openrouter"

    with pytest.raises(ErroConfig, match="não publica"):
        carregar_catalogo("openrouter", lambda nome: SoSintetiza(), tmp_path)


@pytest.mark.parametrize(("idioma", "ids"), [("pt", ["b", "a"]), ("Portuguese", ["b", "a"]),
                                             ("multi", ["d"]), (None, ["b", "a", "c", "d"])])
def test_filtrar_por_idioma(idioma, ids):
    assert [v.id for v in filtrar(VOZES, idioma)] == ids
