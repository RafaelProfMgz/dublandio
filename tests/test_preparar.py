from dublandio.preparar import md_para_roteiro, preparar_livro


def test_disse_nome():
    assert md_para_roteiro("— Vamos. — disse Zoltan Chivay.", []) == "Zoltan: Vamos."


def test_disse_nome_composto_da_lista():
    assert md_para_roteiro("— Pare. — disse Fa Yuiry, sem olhar.", ["Fa Yuiry"]) == "Fa Yuiry: Pare."


def test_pronome_vira_narrador():
    assert md_para_roteiro("— Vamos. — disse ela.", []) == "Narrador: Vamos."


def test_travessao_nome_sem_disse_mantem_a_narracao():
    assert md_para_roteiro("— Agora — Reyes apontou.", []) == "Reyes: Agora\n\nNarrador: Reyes apontou."


def test_contexto_personagem():
    md = "Kamille olhou para a escotilha.\n\n— Não."
    assert md_para_roteiro(md, ["Kamille", "Emma"]) == "Narrador: Kamille olhou para a escotilha.\n\nKamille: Não."


def test_contexto_usa_ultimo_citado():
    md = "Emma empurrou Kamille para trás.\n\n— Fica."
    assert md_para_roteiro(md, ["Emma", "Kamille"]).endswith("Kamille: Fica.")


def test_dialogo_longo_sem_falante_fica_com_narrador():
    fala = "— " + "palavra " * 15
    md = "Kamille entrou.\n\n" + fala
    assert md_para_roteiro(md, ["Kamille"]).splitlines()[-1].startswith("Narrador: ")


def test_remove_titulo_e_italico():
    md = "# Capítulo 3 — A Ponte\n\nO *rio* corria.\nLento."
    assert md_para_roteiro(md, []) == "Narrador: O rio corria. Lento."


def test_preparar_nao_sobrescreve_sem_forcar(livro):
    livro.origem.mkdir(parents=True)
    (livro.origem / "cap_001.md").write_text("Texto novo.", encoding="utf-8")
    livro.dir_roteiro.mkdir(parents=True)
    existente = livro.dir_roteiro / "cap_001.txt"
    existente.write_text("Narrador: editado à mão", encoding="utf-8")

    assert preparar_livro(livro) == []
    assert existente.read_text(encoding="utf-8") == "Narrador: editado à mão"

    assert preparar_livro(livro, forcar=True) == [existente]
    assert existente.read_text(encoding="utf-8") == "Narrador: Texto novo."


def test_preparar_sem_origem_levanta(livro):
    livro.origem = None
    import pytest
    with pytest.raises(ValueError, match="origem"):
        preparar_livro(livro)


def test_contexto_exige_palavra_inteira():
    md = "Kamille pegou a Faca.\n\n— Já."
    assert md_para_roteiro(md, ["Fa Yuiry", "Kamille"]).endswith("Kamille: Já.")


def test_palavra_comum_apos_travessao_nao_e_nome():
    md = "Kamille parou.\n\n— Espere — Mas ninguém esperou."
    assert md_para_roteiro(md, ["Kamille"]).endswith("Kamille: Espere\n\nNarrador: Mas ninguém esperou.")


def test_fala_depois_da_atribuicao_nao_se_perde():
    md = "— Até o navio subir — disse ele. — Quem não entregou até lá, não entregou."
    assert md_para_roteiro(md, []) == "Narrador: Até o navio subir\n\nNarrador: Quem não entregou até lá, não entregou."


def test_atribuicao_sem_nome_nao_inventa_falante():
    # Antes, "Posso" (começo da fala seguinte) virava o nome de quem fala.
    md = "Geralt riu.\n\n— Vou devagar? — perguntou. — Posso pedir licença ao tronco."
    assert md_para_roteiro(md, ["Geralt"]).split("\n\n")[1:] == [
        "Geralt: Vou devagar?", "Geralt: Posso pedir licença ao tronco."]


def test_narracao_longa_depois_do_disse_vai_para_o_narrador():
    md = "— O nome. — perguntou o padeiro, erguendo o braço na direção dele."
    assert md_para_roteiro(md, []) == (
        "Narrador: O nome.\n\nNarrador: perguntou o padeiro, erguendo o braço na direção dele.")


def test_fala_interrompida_pela_narracao():
    md = "— Eu — Ana hesitou — não sei. — disse Ana."
    assert md_para_roteiro(md, []) == "Ana: Eu\n\nNarrador: Ana hesitou\n\nAna: não sei."


def test_limpa_comentario_separador_link_e_citacao():
    md = ("# Prólogo\n<!-- Vol I · nota\ndo autor -->\n\nO _rio_ [corria](x.md).\n\n---\n\n"
          "> Lento.\n\n***\n\n`fim`")
    assert md_para_roteiro(md, []) == "Narrador: O rio corria.\n\nNarrador: Lento.\n\nNarrador: fim"


def test_preparar_segue_a_lista_de_arquivos_e_copia_txt(livro):
    (livro.origem / "vol1" / "arco").mkdir(parents=True)
    (livro.origem / "vol1" / "prologo.md").write_text("# Prólogo\n\nEra uma vez.", encoding="utf-8")
    (livro.origem / "vol1" / "arco" / "cap_01.txt").write_text("Kamille: Já é roteiro.", encoding="utf-8")
    livro.arquivos = ["vol1/prologo.md", "vol1/arco/cap_01.txt"]

    escritos = preparar_livro(livro)
    assert [p.name for p in escritos] == ["cap_001.txt", "cap_002.txt"]
    assert escritos[0].read_text(encoding="utf-8") == "Narrador: Era uma vez."
    assert escritos[1].read_text(encoding="utf-8") == "Kamille: Já é roteiro."


def test_preparar_sem_lista_aceita_txt_e_ignora_outros_nomes(livro):
    livro.origem.mkdir(parents=True)
    (livro.origem / "cap_000.md").write_text("Prólogo.", encoding="utf-8")
    (livro.origem / "cap_001.txt").write_text("Narrador: Um.", encoding="utf-8")
    (livro.origem / "cap_extra.md").write_text("Não é capítulo.", encoding="utf-8")
    assert [p.name for p in preparar_livro(livro)] == ["cap_000.txt", "cap_001.txt"]


def test_preparar_arquivo_listado_que_sumiu(livro):
    import pytest

    livro.origem.mkdir(parents=True)
    livro.arquivos = ["sumiu.md"]
    with pytest.raises(FileNotFoundError, match="sumiu.md"):
        preparar_livro(livro)
