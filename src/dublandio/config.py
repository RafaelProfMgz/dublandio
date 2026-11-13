"""Configuração: variáveis do .env e o livro (livros/<slug>/livro.yaml)."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

PROVEDORES = ("heygen", "openrouter")
NARRADOR = "Narrador"


@dataclass
class Livro:
    slug: str
    titulo: str
    origem: Path | None  # pasta com os cap_*.md do manuscrito
    provedor: str
    idioma: str = "pt"
    reserva: str | None = None  # provedor usado quando o principal esgota (cota, chave)
    personagens: list[str] = field(default_factory=list)
    arquivos: list[str] = field(default_factory=list)  # ordem dos capítulos, relativa à origem
    apelidos: dict[str, str] = field(default_factory=dict)  # nome no roteiro -> canônico
    vozes: dict[str, dict[str, str]] = field(default_factory=dict)  # provedor -> nome -> voz
    raiz: Path = Path(".")
    avatares: dict[str, str] = field(default_factory=dict)  # personagem -> ID do avatar/look HeyGen
    video: dict = field(default_factory=dict)  # opções da geração de vídeo

    # Tudo de um livro fica em livros/<slug>/; só o cache fica de fora.
    @property
    def dir(self) -> Path:
        return self.raiz / "livros" / self.slug

    @property
    def dir_roteiro(self) -> Path:
        return self.dir / "roteiro"

    @property
    def dir_manifesto(self) -> Path:
        return self.dir / "manifesto"

    @property
    def dir_audio(self) -> Path:
        return self.dir / "audio"

    @property
    def dir_cache(self) -> Path:
        return self.raiz / ".cache" / self.slug

    @property
    def provedores(self) -> list[str]:
        """Em ordem de preferência: o principal e, se houver, a reserva."""
        return [self.provedor] + ([self.reserva] if self.reserva else [])

    def nome_canonico(self, nome: str) -> str:
        return self.apelidos.get(nome, nome)

    def tem_voz_propria(self, nome: str) -> bool:
        return self.nome_canonico(nome) in self.vozes.get(self.provedor, {})

    def voz(self, nome: str, provedor: str | None = None) -> str:
        """Voz do personagem no provedor (o do livro, por padrão); sem voz própria, usa a do Narrador."""
        provedor = provedor or self.provedor
        vozes = self.vozes.get(provedor, {})
        canonico = self.nome_canonico(nome)
        if canonico in vozes:
            return vozes[canonico]
        if NARRADOR in vozes:
            return vozes[NARRADOR]
        raise KeyError(f"livro '{self.slug}' não define voz de {NARRADOR} para o provedor {provedor}")


def livros_disponiveis(raiz: Path = Path(".")) -> list[str]:
    pasta = raiz / "livros"
    if not pasta.is_dir():
        return []
    return sorted(p.parent.name for p in pasta.glob("*/livro.yaml"))


def caminho_do_livro(livro: Livro, salvo: str) -> Path:
    """Reencontra arquivos do livro após mover o projeto ou montar /dados no Docker."""
    marcador = f'/livros/{livro.slug}/'
    if marcador in salvo:
        relativo = salvo.split(marcador, 1)[1]
        candidato = (livro.dir / relativo).resolve()
        if candidato.is_relative_to(livro.dir.resolve()):
            return candidato
    return Path(salvo)


def carregar_livro(slug: str, raiz: Path = Path(".")) -> Livro:
    arquivo = raiz / "livros" / slug / "livro.yaml"
    if not arquivo.exists():
        disponiveis = ", ".join(livros_disponiveis(raiz)) or "nenhum"
        raise FileNotFoundError(f"livro '{slug}' não encontrado ({arquivo}). Disponíveis: {disponiveis}")

    return ler_livro(arquivo.read_text(encoding="utf-8"), slug, raiz)


def ler_livro(texto: str, slug: str, raiz: Path = Path(".")) -> Livro:
    """Monta o Livro a partir do texto de um livro.yaml (valida antes de gravar um novo)."""
    arquivo = raiz / "livros" / slug / "livro.yaml"
    try:
        dados = yaml.safe_load(texto) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"YAML inválido em {arquivo}: {e}") from e
    if not isinstance(dados, dict):
        raise ValueError(f"{arquivo} precisa ser um mapa (titulo:, provedor:, vozes: ...)")
    provedor = dados.get("provedor", "heygen")
    if provedor not in PROVEDORES:
        raise ValueError(f"provedor inválido em {arquivo}: '{provedor}' (use {' ou '.join(PROVEDORES)})")

    reserva = dados.get("reserva") or None
    if reserva is not None and (reserva not in PROVEDORES or reserva == provedor):
        raise ValueError(f"reserva inválida em {arquivo}: '{reserva}' (use o outro provedor, não '{provedor}')")

    origem = dados.get("origem")
    arquivos = [str(a) for a in dados.get("arquivos") or []]
    if arquivos and not origem:
        raise ValueError(f"{arquivo} lista 'arquivos' mas não tem 'origem' (a pasta de onde eles vêm)")
    return Livro(
        slug=slug,
        titulo=dados.get("titulo", slug),
        origem=(Path(origem).expanduser() if Path(origem).expanduser().is_absolute() else raiz / origem) if origem else None,
        provedor=provedor,
        reserva=reserva,
        idioma=dados.get("idioma", "pt"),
        personagens=list(dados.get("personagens") or []),
        arquivos=arquivos,
        apelidos=dict(dados.get("apelidos") or {}),
        vozes={k: dict(v or {}) for k, v in (dados.get("vozes") or {}).items()},
        raiz=raiz,
        avatares=dict(dados.get("avatares") or {}),
        video=dict(dados.get("video") or {}),
    )


def definir_voz(texto: str, provedor: str, personagem: str, voz: str) -> str:
    """Altera só a entrada escolhida, preservando comentários e demais provedores."""
    node = yaml.compose(texto)
    caminho = ["vozes", provedor, personagem]
    for i, chave in enumerate(caminho):
        if isinstance(node, yaml.MappingNode):
            encontrado = next((v for k, v in node.value if k.value == chave), None)
            if encontrado is not None:
                node = encontrado
                continue
        valor = voz
        for parte in reversed(caminho[i:]):
            valor = {parte: valor}
        if isinstance(node, yaml.MappingNode):
            if node.flow_style:
                trecho = json.dumps(valor, ensure_ascii=False)[1:-1]
                inicio = node.start_mark.index + 1
                return texto[:inicio] + trecho + (", " if node.value else "") + texto[inicio:]
            inicio = node.start_mark.index
            indent = " " * node.start_mark.column
            trecho = yaml.safe_dump(valor, allow_unicode=True, sort_keys=False).rstrip()
            trecho = trecho.replace("\n", "\n" + indent) + "\n" + indent
            return texto[:inicio] + trecho + texto[inicio:]
        # Um mapa opcional pode estar vazio (vozes: null).
        if node is None:
            return texto + "\n" + yaml.safe_dump(valor, allow_unicode=True, sort_keys=False)
        return texto[:node.start_mark.index] + json.dumps(valor, ensure_ascii=False) + texto[node.end_mark.index:]
    return texto[:node.start_mark.index] + json.dumps(voz, ensure_ascii=False) + texto[node.end_mark.index:]


def salvar_env(path: Path, chave: str, valor: str) -> None:
    """Grava `chave=valor` no .env (troca a linha se ela existir, mantém o resto) e já vale neste processo."""
    linhas = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    nova = f"{chave}={valor}"
    for i, linha in enumerate(linhas):
        if not linha.lstrip().startswith("#") and linha.split("=", 1)[0].strip() == chave:
            linhas[i] = nova
            break
    else:
        linhas.append(nova)
    # Reescreve o mesmo arquivo em vez de trocar por outro: no Docker ele pode estar montado.
    path.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    os.environ[chave] = valor


def carregar_env(path: Path = Path(".env")) -> None:
    """Lê KEY=valor do .env sem sobrescrever variáveis já definidas no ambiente."""
    if not path.exists():
        return
    for linha in path.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave, valor = chave.strip(), valor.strip().strip('"').strip("'")
        if chave and valor and not os.getenv(chave):
            os.environ[chave] = valor
