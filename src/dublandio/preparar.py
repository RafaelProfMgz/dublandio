"""Estágio 1: capítulo em Markdown -> roteiro "Nome: fala" (blocos separados por linha vazia).

A identificação de quem fala é heurística; o roteiro gerado é para ser revisado
e pode ser editado à mão (por isso não é sobrescrito sem --forcar).
"""

import re
from pathlib import Path

from dublandio.config import NARRADOR, Livro

# Um parágrafo de diálogo alterna fala e narração separadas por travessão:
# "— fala — disse Nome, sem olhar. — mais fala — Nome deu as costas."
_SEPARADOR = re.compile(r"\s+—\s+")
# Narração que é só a atribuição: "disse Nome", "perguntou." (o nome pode ter várias palavras)
_ATRIBUICAO = re.compile(
    r"^(?:disse|perguntou|respondeu|gritou|murmurou)\b\s*(?P<nome>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]*?)?\s*(?:[,.;!?]|$)"
)
# Depois de tirar a atribuição, sobra quanto texto para valer como narração ("sem olhar." não vale).
_MIN_NARRACAO = 4
_NOME = re.compile(r"[A-ZÀ-Ý][a-zà-ÿ]+")

_NAO_SAO_NOMES = {"ela", "ele", "a", "o", "mulher", "homem", "velho", "velha", "alguém"}
# Palavras que abrem a narração depois do travessão ("— Vamos — Mas ninguém se mexeu").
_PALAVRAS_COMUNS = _NAO_SAO_NOMES | {
    "um", "uma", "os", "as", "eu", "nós", "eles", "elas", "mas", "não", "sim", "ou", "se", "e",
    "então", "quando", "depois", "agora", "já", "só", "foi", "era", "tem", "no", "na", "nos", "nas",
    "de", "do", "da", "por", "para", "com", "nem", "aí", "isso", "aquilo", "ninguém", "todos",
    "você", "vocês", "que", "quem", "como", "onde", "outro", "outra", "esse", "essa", "este", "esta",
    "aquele", "aquela", "ainda", "também", "mais", "muito", "pois", "porque", "talvez", "nada", "tudo",
}
# Diálogo sem falante identificado só herda o contexto se for curto e não narrar ação.
_MAX_FALA_CONTEXTO = 80
_VERBOS_DE_ACAO = ("disse", "parou", "levantou")


def _limpar(md: str) -> str:
    """Tira do Markdown o que não é para ser lido em voz alta."""
    md = re.sub(r"<!--.*?-->", "", md, flags=re.DOTALL)  # comentários (notas do autor)
    md = re.sub(r"^\s*#.*$", "", md, flags=re.MULTILINE)  # títulos
    md = re.sub(r"^[ \t]*([-*_])([ \t]*\1){2,}[ \t]*$", "", md, flags=re.MULTILINE)  # separadores: --- *** ___
    md = re.sub(r"^[ \t]*>[ \t]?", "", md, flags=re.MULTILINE)  # citações
    md = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", md)  # links e imagens: fica só o texto
    md = re.sub(r"(?<!\w)_(\S(?:.*?\S)?)_(?!\w)", r"\1", md)  # _itálico_
    return md.replace("*", "").replace("`", "")  # itálico/negrito, código


def _paragrafos(texto: str) -> list[str]:
    blocos = re.split(r"\n\s*\n", texto)
    return [" ".join(l.strip() for l in b.splitlines() if l.strip()) for b in blocos if b.strip()]


def _nome_do_falante(bruto: str, personagens: list[str]) -> str:
    bruto = bruto.strip()
    for p in personagens:  # nome completo da lista ganha ("Fa Yuiry", não "Fa")
        if bruto == p or bruto.startswith(p + " ") or bruto == p.split()[0]:
            return p
    primeiro = bruto.split()[0] if bruto.split() else NARRADOR
    return NARRADOR if primeiro.lower() in _NAO_SAO_NOMES else primeiro


def _ultimo_citado(paragrafo: str, personagens: list[str]) -> str | None:
    """Personagem citado mais perto do fim do parágrafo (nome completo ou primeiro nome)."""
    melhor, posicao = None, -1
    for p in personagens:
        for forma in {p, p.split()[0]}:
            for m in re.finditer(rf"\b{re.escape(forma)}\b", paragrafo):
                if m.start() > posicao:
                    melhor, posicao = p, m.start()
    return melhor


def _falante(narracoes: list[str], personagens: list[str]) -> str | None:
    """Quem fala, pela 1ª narração que diz: "disse Nome" ou "Nome fez algo"."""
    for n in narracoes:
        if m := _ATRIBUICAO.match(n):
            if m["nome"] and m["nome"].strip():
                return _nome_do_falante(m["nome"], personagens)
            continue  # "perguntou." sem nome: tenta a próxima narração
        primeira = n.split()[0].strip(",.;:!?") if n.split() else ""
        if _NOME.fullmatch(primeira) and primeira.lower() not in _PALAVRAS_COMUNS:
            return _nome_do_falante(n, personagens)
    return None


def _narracao(segmento: str) -> str:
    """O que da narração vai para o Narrador: a atribuição sozinha ("disse ela.") não."""
    m = _ATRIBUICAO.match(segmento)
    if m and len(segmento[m.end():].split()) < _MIN_NARRACAO:
        return ""
    return segmento


def md_para_roteiro(md: str, personagens: list[str]) -> str:
    linhas: list[str] = []
    contexto = NARRADOR
    for p in _paragrafos(_limpar(md)):
        if not p.startswith("—"):
            linhas.append(f"{NARRADOR}: {p}")
            contexto = _ultimo_citado(p, personagens) or contexto
            continue

        # Nenhum trecho do parágrafo se perde: as falas vão para quem fala, a narração
        # entre elas para o Narrador (menos a atribuição sozinha, que no áudio sobra).
        segmentos = _SEPARADOR.split(re.sub(r"^—\s*", "", p))
        falante = _falante(segmentos[1::2], personagens)
        if falante is None:
            fala = segmentos[0]
            curta = len(fala) < _MAX_FALA_CONTEXTO and not any(v in fala[:50] for v in _VERBOS_DE_ACAO)
            falante = contexto if curta else NARRADOR
        for i, segmento in enumerate(segmentos):
            if i % 2 == 0:
                linhas.append(f"{falante}: {segmento}")
            elif texto := _narracao(segmento):
                linhas.append(f"{NARRADOR}: {texto}")
    return "\n\n".join(linhas)


CAP = re.compile(r"cap_\d{3}")  # nome de capítulo na origem e no roteiro
EXTENSOES = (".md", ".txt")


def fontes(livro: Livro) -> list[tuple[str, Path]]:
    """(capítulo, arquivo de origem) na ordem do livro.

    Com `arquivos` no livro.yaml, o 1º arquivo da lista vira cap_001, o 2º cap_002...
    Sem a lista, vale o nome: origem/cap_NNN.md (ou .txt) vira o roteiro cap_NNN.
    """
    if livro.origem is None:
        raise ValueError(f"livro '{livro.slug}' não tem 'origem' no livro.yaml: não há o que preparar")
    if not livro.origem.is_dir():
        raise FileNotFoundError(f"pasta de origem não existe: {livro.origem}")
    if livro.arquivos:
        return [(f"cap_{i:03d}", livro.origem / a) for i, a in enumerate(livro.arquivos, 1)]
    return [(p.stem, p) for p in sorted(livro.origem.glob("cap_*"))
            if p.suffix in EXTENSOES and CAP.fullmatch(p.stem)]


def preparar_livro(livro: Livro, forcar: bool = False) -> list[Path]:
    """Gera livros/<slug>/roteiro/cap_NNN.txt a partir da origem. Retorna os escritos.

    `.md` é convertido (quem fala em cada parágrafo); `.txt` já é roteiro e é copiado como está.
    """
    lista = fontes(livro)
    livro.dir_roteiro.mkdir(parents=True, exist_ok=True)
    escritos = []
    for cap, origem in lista:
        destino = livro.dir_roteiro / f"{cap}.txt"
        if destino.exists() and not forcar:
            continue
        if not origem.is_file():
            raise FileNotFoundError(f"arquivo listado no livro.yaml não existe: {origem}")
        texto = origem.read_text(encoding="utf-8")
        if origem.suffix == ".md":
            texto = md_para_roteiro(texto, livro.personagens)
        destino.write_text(texto, encoding="utf-8")
        escritos.append(destino)
    return escritos
