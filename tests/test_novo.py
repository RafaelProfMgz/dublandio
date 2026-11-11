import pytest

from dublandio.config import carregar_livro
from dublandio.novo import criar_livro, parece_capitulo, slugificar, textos_da_pasta
from dublandio.preparar import fontes


@pytest.fixture
def pasta(tmp_path):
    origem = tmp_path / "manuscrito"
    (origem / "arco_10").mkdir(parents=True)
    (origem / "arco_2").mkdir()
    (origem / ".oculta").mkdir()
    for nome in ["arco_10/cap_01.md", "arco_2/cap_01.md", "arco_2/resumo_arco.md", "README.md", "prologo.txt",
                 "epilogo.md", ".oculta/x.md"]:
        (origem / nome).write_text("Texto.", encoding="utf-8")
    (origem / "capa.png").write_bytes(b"")
    return origem


def test_slugificar():
    assert slugificar("A Árvore do Ciclo: Vol. 1") == "a-arvore-do-ciclo-vol-1"
    assert slugificar("A 33ª Expedição") == "a-33a-expedicao"


def test_textos_em_ordem_natural_sem_ocultos(pasta):
    assert textos_da_pasta(pasta) == ["prologo.txt", "arco_2/cap_01.md", "arco_2/resumo_arco.md", "arco_10/cap_01.md",
                                      "README.md", "epilogo.md"]


def test_parece_capitulo():
    assert parece_capitulo("arco_2/cap_01.md") and parece_capitulo("prologo.txt")
    assert not parece_capitulo("arco_2/resumo_arco.md") and not parece_capitulo("README.md")


def test_cria_livro_com_lista_e_reserva(tmp_path, pasta):
    livro = criar_livro(tmp_path, "Entre: Mundos", pasta, ["prologo.txt", "arco_2/cap_01.md"],
                        personagens=["Anselmo", " ", "Velha Creux"])
    assert livro.slug == "entre-mundos"
    lido = carregar_livro("entre-mundos", tmp_path)
    assert lido.titulo == "Entre: Mundos" and lido.origem == pasta
    assert lido.provedores == ["heygen", "openrouter"]
    assert lido.personagens == ["Anselmo", "Velha Creux"]
    assert [(c, o.name) for c, o in fontes(lido)] == [("cap_001", "prologo.txt"), ("cap_002", "cap_01.md")]
    assert lido.voz("Ninguém") == "049413e41c334753984c294d694afb5c"
    assert lido.voz("Ninguém", "openrouter") == "lucian"


def test_pasta_no_padrao_dispensa_a_lista(tmp_path):
    origem = tmp_path / "vol1"
    origem.mkdir()
    for n in ["cap_000.md", "cap_001.md"]:
        (origem / n).write_text("Texto.", encoding="utf-8")
    criar_livro(tmp_path, "Livro", origem, ["cap_000.md", "cap_001.md"], reserva=None)
    texto = (tmp_path / "livros" / "livro" / "livro.yaml").read_text(encoding="utf-8")
    assert "arquivos" not in texto and "reserva" not in texto
    assert [c for c, _ in fontes(carregar_livro("livro", tmp_path))] == ["cap_000", "cap_001"]


def test_recusa_livro_repetido_e_arquivo_de_fora(tmp_path, pasta):
    criar_livro(tmp_path, "X", pasta, ["prologo.txt"])
    with pytest.raises(ValueError, match="já existe"):
        criar_livro(tmp_path, "X", pasta, ["prologo.txt"])
    with pytest.raises(ValueError, match="não é um .md ou .txt"):
        criar_livro(tmp_path, "Y", pasta, ["../fora.md"])
    with pytest.raises(ValueError, match="não é um .md ou .txt"):
        criar_livro(tmp_path, "Z", pasta, ["capa.png"])


def test_sem_lista_e_sem_padrao_pede_os_arquivos(tmp_path, pasta):
    with pytest.raises(ValueError, match="escolha quais arquivos"):
        criar_livro(tmp_path, "X", pasta)
    assert not (tmp_path / "livros" / "x").exists()
