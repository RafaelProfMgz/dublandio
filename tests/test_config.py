from pathlib import Path

import pytest

from dublandio.config import carregar_env, carregar_livro, ler_livro


def test_voz_resolve_apelido(livro):
    assert livro.voz("Ele") == "X"


def test_voz_fallback_narrador(livro):
    assert livro.voz("Desconhecido") == "N"


def test_voz_sem_narrador_levanta(livro):
    livro.vozes["heygen"].pop("Narrador")
    with pytest.raises(KeyError):
        livro.voz("Desconhecido")


def test_pastas_ficam_dentro_do_livro(livro, tmp_path):
    base = tmp_path / "livros" / "exemplo"
    assert livro.dir == base
    assert livro.dir_roteiro == base / "roteiro"
    assert livro.dir_manifesto == base / "manifesto"
    assert livro.dir_audio == base / "audio"
    assert livro.dir_cache == tmp_path / ".cache" / "exemplo"


def _escrever(raiz: Path, slug: str, yaml: str) -> None:
    pasta = raiz / "livros" / slug
    pasta.mkdir(parents=True)
    (pasta / "livro.yaml").write_text(yaml, encoding="utf-8")


def test_carregar_livro_expande_til(tmp_path):
    _escrever(tmp_path, "a", "titulo: A\norigem: ~/livros/a\nprovedor: heygen\nvozes:\n  heygen: {Narrador: N}\n")
    livro = carregar_livro("a", raiz=tmp_path)
    assert livro.origem == Path.home() / "livros" / "a"
    assert livro.idioma == "pt"
    assert livro.apelidos == {}


def test_livro_sem_origem(tmp_path):
    _escrever(tmp_path, "b", "titulo: B\nprovedor: openrouter\nvozes:\n  openrouter: {Narrador: lucian}\n")
    assert carregar_livro("b", raiz=tmp_path).origem is None


def test_livro_inexistente_lista_disponiveis(tmp_path):
    _escrever(tmp_path, "existe", "titulo: E\nprovedor: heygen\nvozes: {}\n")
    with pytest.raises(FileNotFoundError, match="existe"):
        carregar_livro("nao-existe", raiz=tmp_path)


def test_provedor_invalido(tmp_path):
    _escrever(tmp_path, "c", "titulo: C\nprovedor: outro\nvozes: {}\n")
    with pytest.raises(ValueError, match="provedor"):
        carregar_livro("c", raiz=tmp_path)


def test_carregar_env_nao_sobrescreve(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comentário\nA_TESTE="novo"\nB_TESTE=b\n', encoding="utf-8")
    monkeypatch.setenv("A_TESTE", "antigo")
    monkeypatch.delenv("B_TESTE", raising=False)
    carregar_env(env)
    import os
    assert os.environ["A_TESTE"] == "antigo"
    assert os.environ["B_TESTE"] == "b"


def test_ler_livro_yaml_invalido(tmp_path):
    with pytest.raises(ValueError, match="YAML inválido"):
        ler_livro("vozes: [", "ex", tmp_path)


def test_ler_livro_exige_mapa(tmp_path):
    with pytest.raises(ValueError, match="mapa"):
        ler_livro("- só uma lista", "ex", tmp_path)


def test_reserva_entra_depois_do_principal(tmp_path):
    livro = ler_livro("provedor: heygen\nreserva: openrouter\n", "ex", tmp_path)
    assert livro.provedores == ["heygen", "openrouter"]
    assert ler_livro("provedor: heygen\n", "ex", tmp_path).provedores == ["heygen"]


@pytest.mark.parametrize("reserva", ["heygen", "outro"])
def test_reserva_invalida(tmp_path, reserva):
    with pytest.raises(ValueError, match="reserva inválida"):
        ler_livro(f"provedor: heygen\nreserva: {reserva}\n", "ex", tmp_path)


def test_voz_em_outro_provedor(livro):
    assert livro.voz("Ele", "openrouter") == "lucian"  # sem voz própria lá: a do Narrador


def test_salvar_env_troca_a_linha_e_mantem_o_resto(tmp_path, monkeypatch):
    from dublandio.config import salvar_env

    monkeypatch.delenv("HEYGEN_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("# comentário\nOPENROUTER_API_KEY=or\nHEYGEN_API_KEY=\n", encoding="utf-8")
    salvar_env(env, "HEYGEN_API_KEY", "nova")
    assert env.read_text(encoding="utf-8") == "# comentário\nOPENROUTER_API_KEY=or\nHEYGEN_API_KEY=nova\n"
    import os
    assert os.environ["HEYGEN_API_KEY"] == "nova"


def test_salvar_env_cria_o_arquivo(tmp_path, monkeypatch):
    from dublandio.config import salvar_env

    monkeypatch.delenv("HEYGEN_API_KEY", raising=False)
    salvar_env(tmp_path / ".env", "HEYGEN_API_KEY", "k")
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "HEYGEN_API_KEY=k\n"
