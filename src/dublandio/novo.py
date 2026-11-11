"""Cria livros/<slug>/livro.yaml a partir de uma pasta com os capítulos em .md ou .txt."""

import re
import os
import shutil
import tempfile
import unicodedata
from pathlib import Path

import yaml

from dublandio.config import NARRADOR, PROVEDORES, Livro, ler_livro
from dublandio.preparar import CAP, EXTENSOES

# Lucian nos dois provedores (é a mesma voz da HeyGen): trocar para a reserva não muda o narrador.
VOZES_PADRAO = {
    "heygen": {NARRADOR: "049413e41c334753984c294d694afb5c"},
    "openrouter": {NARRADOR: "lucian"},
}
_NAO_CAPITULO = re.compile(r"^(readme|resumo|license|licen[cç]a|notas?|indice|índice|sumario|sumário)", re.IGNORECASE)


def slugificar(texto: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")


_PROLOGO = re.compile(r"pr[oó]logo", re.IGNORECASE)
_EPILOGO = re.compile(r"ep[ií]logo", re.IGNORECASE)


def _ordem_natural(caminho: str) -> tuple:
    # Prólogo primeiro, epílogo por último; no resto, "cap_2" antes de "cap_10".
    nome = Path(caminho).name
    lugar = 0 if _PROLOGO.search(nome) else 2 if _EPILOGO.search(nome) else 1
    return lugar, [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", caminho)]


def textos_da_pasta(pasta: Path, limite: int = 2000) -> list[str]:
    """Arquivos .md/.txt da pasta e subpastas (caminhos relativos, em ordem natural), sem pastas ocultas."""
    achados = []
    for atual, diretorios, arquivos in os.walk(pasta, followlinks=False):
        diretorios[:] = sorted(d for d in diretorios if not d.startswith('.'))
        for nome in sorted(arquivos):
            p = Path(atual) / nome
            if (not nome.startswith('.') and p.suffix in EXTENSOES and p.is_file()
                    and p.resolve().is_relative_to(pasta.resolve())):
                achados.append(p.relative_to(pasta).as_posix())
                if len(achados) >= limite:
                    return sorted(achados, key=_ordem_natural)
    return sorted(achados, key=_ordem_natural)


def parece_capitulo(caminho: str) -> bool:
    """README, resumos e notas ficam desmarcados por padrão ao escolher os capítulos."""
    return not _NAO_CAPITULO.match(Path(caminho).name)


def _no_padrao(origem: Path, arquivos: list[str]) -> bool:
    """Os arquivos são exatamente os cap_NNN.* da pasta, na ordem dos nomes: dispensa a lista."""
    if not all("/" not in a and CAP.fullmatch(Path(a).stem) for a in arquivos):
        return False
    padrao = sorted(p.name for p in origem.glob("cap_*") if p.suffix in EXTENSOES and CAP.fullmatch(p.stem))
    return arquivos == padrao


def _y(valor) -> str:
    """Valor YAML numa linha, com aspas só quando precisa."""
    return yaml.safe_dump(valor, allow_unicode=True, default_flow_style=True, width=10_000).removesuffix("...\n").strip()


def _caminho_legivel(p: Path) -> str:
    try:
        return "~/" + p.relative_to(Path.home()).as_posix()
    except ValueError:
        return p.as_posix()


def criar_livro(
    raiz: Path,
    titulo: str,
    origem: Path,
    arquivos: list[str] | None = None,
    provedor: str = "heygen",
    reserva: str | None = "openrouter",
    personagens: list[str] | None = None,
    slug: str | None = None,
) -> Livro:
    """Escreve livros/<slug>/livro.yaml. Sem `arquivos`, vale o padrão origem/cap_NNN.(md|txt)."""
    titulo = titulo.strip()
    slug = slugificar(slug or titulo)
    if not titulo or not slug:
        raise ValueError("dê um título ao livro")
    if (raiz / "livros" / slug).exists():
        raise ValueError(f"já existe um livro '{slug}' em livros/; escolha outro nome")
    origem = origem.expanduser().resolve()
    if not origem.is_dir():
        raise FileNotFoundError(f"pasta não existe: {origem}")
    if provedor not in PROVEDORES:
        raise ValueError(f"provedor inválido: '{provedor}' (use {' ou '.join(PROVEDORES)})")
    reserva = reserva if reserva and reserva != provedor else None

    arquivos = list(arquivos or [])
    for a in arquivos:
        caminho = (origem / a).resolve()
        if not caminho.is_relative_to(origem) or caminho.suffix not in EXTENSOES or not caminho.is_file():
            raise ValueError(f"'{a}' não é um .md ou .txt dentro de {origem}")
    if arquivos and _no_padrao(origem, arquivos):
        arquivos = []  # é o padrão: o livro.yaml fica sem a lista
    if not arquivos and not any(CAP.fullmatch(p.stem) for p in origem.glob("cap_*") if p.suffix in EXTENSOES):
        raise ValueError(f"nenhum cap_NNN.md ou .txt em {origem}: escolha quais arquivos são os capítulos")

    linhas = [
        f"titulo: {_y(titulo)}",
        f"origem: {_y(_caminho_legivel(origem))}",
        f"provedor: {provedor}          # heygen | openrouter",
    ]
    if reserva:
        linhas.append(f"reserva: {reserva}       # se a cota do principal acabar, a síntese continua aqui")
    linhas += [
        "idioma: pt",
        "",
        "# Usados pelo `preparar` para adivinhar quem fala quando o diálogo não diz.",
        f"personagens: {_y([p.strip() for p in personagens or [] if p.strip()])}",
    ]
    if arquivos:
        linhas += ["", "# Ordem dos capítulos (relativa à origem): o 1º vira cap_001, o 2º cap_002...", "arquivos:"]
        linhas += [f"  - {_y(a)}" for a in arquivos]
    linhas += [
        "",
        "# Nome que aparece no roteiro -> nome canônico (o que tem voz).",
        "apelidos: {}",
        "",
        "# Personagem sem voz aqui usa a do Narrador. Escolha vozes na aba Catálogo da interface.",
        "vozes:",
    ]
    for nome in [provedor] + ([reserva] if reserva else []):
        linhas.append(f"  {nome}:")
        voz = VOZES_PADRAO[nome][NARRADOR]
        linhas.append(f"    {NARRADOR}: {voz}" + ("  # lucian" if nome == "heygen" else ""))
    texto = "\n".join(linhas) + "\n"

    livro = ler_livro(texto, slug, raiz)  # confere antes de gravar
    livro.dir.mkdir(parents=True)
    (livro.dir / "livro.yaml").write_text(texto, encoding="utf-8")
    return livro


def importar_livro(raiz: Path, titulo: str, arquivos: list[tuple[str, bytes]], **opcoes) -> Livro:
    """Recebe capítulos do navegador e guarda a origem junto ao livro, inclusive no Docker."""
    if not arquivos:
        raise ValueError('escolha ao menos um capítulo .md ou .txt')
    cache = raiz / '.cache' / 'importacoes'
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as temporario:
        trabalho = Path(temporario)
        origem = trabalho / 'origem'
        origem.mkdir()
        nomes = []
        for nome, dados in arquivos:
            p = Path(nome)
            if (p.is_absolute() or '..' in p.parts or '\\' in nome or p.suffix not in EXTENSOES
                    or any(parte.startswith('.') for parte in p.parts)):
                raise ValueError(f'nome de capítulo inválido: {nome}')
            if nome in nomes:
                raise ValueError(f'arquivo repetido: {nome}')
            try:
                texto = dados.decode('utf-8-sig')
            except UnicodeDecodeError as e:
                raise ValueError(f'{nome}: salve o arquivo em UTF-8 antes de importar') from e
            destino = origem / p
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(texto, encoding='utf-8')
            nomes.append(nome)
        lv = criar_livro(trabalho, titulo, origem, nomes, **opcoes)
        destino = raiz / 'livros' / lv.slug
        if destino.exists():
            raise ValueError(f"já existe um livro '{lv.slug}'; escolha outro título")
        shutil.copytree(origem, lv.dir / 'originais')
        config = lv.dir / 'livro.yaml'
        texto = config.read_text(encoding='utf-8')
        texto = re.sub(r'^origem:.*$', 'origem: ' + _y(f'livros/{lv.slug}/originais'), texto, count=1, flags=re.MULTILINE)
        config.write_text(texto, encoding='utf-8')
        destino.parent.mkdir(parents=True, exist_ok=True)
        lv.dir.rename(destino)
        return ler_livro(texto, lv.slug, raiz)
