from pathlib import Path

import pytest

from dublandio.config import Livro


@pytest.fixture
def livro(tmp_path: Path) -> Livro:
    """Livro mínimo em pasta temporária, com vozes nos dois provedores."""
    return Livro(
        slug="exemplo",
        titulo="Exemplo",
        origem=tmp_path / "origem",
        provedor="heygen",
        idioma="pt",
        personagens=["Kamille", "Fa Yuiry"],
        apelidos={"Ele": "Fonoti", "Fa": "Fa Yuiry"},
        vozes={
            "heygen": {"Narrador": "N", "Fonoti": "X", "Fa Yuiry": "F"},
            "openrouter": {"Narrador": "lucian"},
        },
        raiz=tmp_path,
    )
