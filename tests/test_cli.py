from pathlib import Path

import pytest

from dublandio.cli import main


@pytest.fixture
def projeto(tmp_path, monkeypatch):
    pasta = tmp_path / "livros" / "ex"
    (pasta / "roteiro").mkdir(parents=True)
    (pasta / "livro.yaml").write_text(
        "titulo: Ex\nprovedor: heygen\napelidos: {Ele: Fonoti}\nvozes:\n  heygen: {Narrador: N, Fonoti: X}\n",
        encoding="utf-8",
    )
    (pasta / "roteiro" / "cap_001.txt").write_text("Ele: Oi.\n\nKamille: Tchau.\n\nA porta bateu.", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return pasta


def test_livro_inexistente_retorna_2(projeto, capsys):
    assert main(["vozes", "nao-existe"]) == 2
    assert "Disponíveis: ex" in capsys.readouterr().err


def test_livros_lista(projeto, capsys):
    assert main(["livros"]) == 0
    assert capsys.readouterr().out.strip() == "ex"


def test_separar_gera_manifestos(projeto):
    assert main(["separar", "ex"]) == 0
    assert (projeto / "manifesto" / "cap_001.json").exists()


def test_vozes_lista_fallback(projeto, capsys):
    main(["separar", "ex"])
    capsys.readouterr()
    assert main(["vozes", "ex"]) == 0
    saida = capsys.readouterr().out
    assert "Fonoti" in saida and "X" in saida
    linha_kamille = next(l for l in saida.splitlines() if "Kamille" in l)
    assert "sem voz própria" in linha_kamille


def test_sintetizar_sem_chave_retorna_2(projeto, monkeypatch, capsys):
    monkeypatch.delenv("HEYGEN_API_KEY", raising=False)
    main(["separar", "ex"])
    assert main(["sintetizar", "ex"]) == 2
    assert "HEYGEN_API_KEY" in capsys.readouterr().err


def test_preparar_sem_origem_retorna_2(projeto, capsys):
    assert main(["preparar", "ex"]) == 2
    assert "origem" in capsys.readouterr().err


def test_catalogo_filtra_por_idioma(projeto, monkeypatch, capsys):
    from dublandio.tts import Voz

    class ComLista:
        nome = "heygen"

        def listar_vozes(self):
            return [Voz("id-pt", "Yuri", "Portuguese", "male"), Voz("id-en", "Leanne", "English", "female")]

    monkeypatch.setattr("dublandio.cli.criar_provedor", lambda nome: ComLista())
    assert main(["catalogo", "--idioma", "pt"]) == 0
    saida = capsys.readouterr().out
    assert "id-pt" in saida and "Yuri" in saida and "id-en" not in saida


def test_catalogo_sem_chave_retorna_2(projeto, monkeypatch, capsys):
    monkeypatch.delenv("HEYGEN_API_KEY", raising=False)
    assert main(["catalogo"]) == 2
    assert "HEYGEN_API_KEY" in capsys.readouterr().err


def test_sintetizar_cota_esgotada_para_e_avisa(projeto, monkeypatch, capsys):
    from dublandio.tts import ErroTTS

    class SemCota:
        nome = "heygen"

        def sintetizar(self, texto, voz, idioma):
            raise ErroTTS("cota diária acabou", interromper=True)

    monkeypatch.setattr("dublandio.cli.criar_provedor", lambda nome: SemCota())
    main(["separar", "ex"])
    assert main(["sintetizar", "ex"]) == 1
    assert "síntese interrompida: cota diária acabou" in capsys.readouterr().out


def test_novo_sem_padrao_usa_os_textos_que_parecem_capitulo(projeto, tmp_path, capsys):
    from dublandio.config import carregar_livro

    origem = tmp_path / "manuscrito" / "arco_1"
    origem.mkdir(parents=True)
    for nome in ["cap_02.md", "cap_01.md", "resumo_arco.md"]:
        (origem / nome).write_text("Texto.", encoding="utf-8")
    assert main(["novo", str(tmp_path / "manuscrito"), "--titulo", "Entre Mundos", "--reserva", ""]) == 0
    saida = capsys.readouterr().out
    assert "cap_001 <- arco_1/cap_01.md" in saida and "cap_002 <- arco_1/cap_02.md" in saida
    livro = carregar_livro("entre-mundos")
    assert livro.arquivos == ["arco_1/cap_01.md", "arco_1/cap_02.md"] and livro.reserva is None


def test_novo_pasta_inexistente_retorna_2(projeto, capsys):
    assert main(["novo", "/nao/existe", "--titulo", "X"]) == 2
    assert "não existe" in capsys.readouterr().err


def test_gui_repassa_host_e_porta(projeto, monkeypatch):
    chamadas = []
    monkeypatch.setattr("dublandio.gui.servidor.rodar", lambda **kw: chamadas.append(kw))
    assert main(["gui", "--host", "0.0.0.0", "--porta", "9000", "--sem-navegador"]) == 0
    assert chamadas == [{"porta": 9000, "abrir": False, "host": "0.0.0.0"}]


def test_gui_escuta_so_local_por_padrao(projeto, monkeypatch):
    chamadas = []
    monkeypatch.setattr("dublandio.gui.servidor.rodar", lambda **kw: chamadas.append(kw))
    assert main(["gui", "--sem-navegador"]) == 0
    assert chamadas[0]["host"] == "127.0.0.1"
