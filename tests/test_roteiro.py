from dublandio.roteiro import Fala, contar_personagens, ler_manifesto, parse_roteiro, separar_livro


def test_parse_nome_e_fala(livro):
    assert parse_roteiro("Fonoti: Janta.", livro) == [Fala(1, "Fonoti", "X", "Janta.")]


def test_sem_prefixo_e_narrador(livro):
    assert parse_roteiro("A nave tremeu.", livro) == [Fala(1, "Narrador", "N", "A nave tremeu.")]


def test_dois_pontos_na_narrativa(livro):
    texto = "Era assim: frio e escuro."
    assert parse_roteiro(texto, livro) == [Fala(1, "Narrador", "N", texto)]


def test_prefixo_longo_e_narrador(livro):
    texto = "O comandante da nave de transporte Temptation: ninguém"
    assert parse_roteiro(texto, livro)[0].personagem == "Narrador"


def test_apelido_aplicado(livro):
    falas = parse_roteiro("Ele: Vamos.\n\nFa: Não.", livro)
    assert [(f.personagem, f.voz) for f in falas] == [("Fonoti", "X"), ("Fa Yuiry", "F")]


def test_bloco_vazio_ignorado(livro):
    falas = parse_roteiro("Narrador: Um.\n\n   \n\nNarrador:   \n\nNarrador: Dois.", livro)
    assert [(f.ordem, f.texto) for f in falas] == [(1, "Um."), (2, "Dois.")]


def test_quebra_interna_vira_espaco(livro):
    assert parse_roteiro("Narrador: linha um\nlinha dois", livro)[0].texto == "linha um linha dois"


def test_separar_e_roundtrip(livro):
    livro.dir_roteiro.mkdir(parents=True)
    (livro.dir_roteiro / "cap_002.txt").write_text("Ele: Olá.\n\nTchau.", encoding="utf-8")
    [manifesto] = separar_livro(livro)
    assert manifesto == livro.dir_manifesto / "cap_002.json"
    assert "Olá" in manifesto.read_text(encoding="utf-8")  # sem escapar acentos
    assert ler_manifesto(manifesto) == [Fala(1, "Fonoti", "X", "Olá."), Fala(2, "Narrador", "N", "Tchau.")]


def test_nome_com_abreviacao(livro):
    assert parse_roteiro("Sra. Thorne: Saia.", livro)[0].personagem == "Sra. Thorne"


def test_contar_personagens_soma_manifestos(livro):
    livro.dir_roteiro.mkdir(parents=True)
    (livro.dir_roteiro / "cap_001.txt").write_text("Ele: Oi.\n\nA porta bateu.", encoding="utf-8")
    (livro.dir_roteiro / "cap_002.txt").write_text("Fa: Tchau.\n\nEle: Até.", encoding="utf-8")
    separar_livro(livro)
    assert contar_personagens(livro) == {"Fonoti": 2, "Narrador": 1, "Fa Yuiry": 1}
