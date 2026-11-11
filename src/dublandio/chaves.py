"""Situação das chaves dos provedores: se existe, se o provedor aceita e se ainda há crédito ou cota.

Conferir a chave não gasta crédito, mas a cota diária da HeyGen (e o crédito dela) só
aparece quando uma síntese esbarra no limite. Por isso o último erro desse tipo de cada
provedor fica anotado em .cache/chaves.json, junto com a impressão da chave: trocar a
chave no .env esquece o erro, e a cota anotada vale só até o fim do dia.
"""

import hashlib
import json
import os
import threading
from collections.abc import Callable
from datetime import date
from pathlib import Path

from dublandio.tts import VARIAVEIS, ErroConfig, ErroTTS, Provedor, Verificacao

ROTULOS = {"heygen": "HeyGen", "openrouter": "OpenRouter"}
ARTIGOS = {"heygen": "a", "openrouter": "o"}
# Onde a pessoa pega a chave e onde compra crédito.
LINKS_CHAVE = {"heygen": "https://app.heygen.com/settings?nav=API", "openrouter": "https://openrouter.ai/settings/keys"}
LINKS_CREDITO = {"heygen": "https://app.heygen.com/settings?nav=Subscriptions", "openrouter": "https://openrouter.ai/settings/credits"}
# ErroTTS.motivo -> situação mostrada na interface
SITUACAO_DO_MOTIVO = {"chave": "invalida", "credito": "sem_credito", "cota": "cota"}
# Situações em que o provedor não sintetiza nada até alguém resolver.
BLOQUEIAM = ("ausente", "invalida", "sem_credito", "cota")
CURTOS = {"ok": "funcionando", "ausente": "sem chave", "invalida": "chave recusada",
          "sem_credito": "sem crédito", "cota": "cota do dia acabou", "indisponivel": "não deu para conferir"}


def impressao(chave: str | None) -> str:
    return hashlib.sha256((chave or "").encode()).hexdigest()[:12]


def mensagem(provedor: str, situacao: str, detalhe: str = "") -> str:
    rotulo, variavel = ROTULOS.get(provedor, provedor), VARIAVEIS.get(provedor, "")
    artigo = ARTIGOS.get(provedor, "o")
    de = f"d{artigo} {rotulo}"  # "da HeyGen", "do OpenRouter"
    textos = {
        "ok": f"A chave {de} está funcionando.",
        "ausente": f"Falta a chave {de}. Use Colocar chave e cole a chave da sua conta "
                   f"(ela fica no arquivo .env, como {variavel}).",
        "invalida": f"{artigo.upper()} {rotulo} recusou a chave salva. Use Trocar chave e cole a chave "
                    "da sua conta, inteira.",
        "sem_credito": f"Acabaram os créditos {de}. Adicione créditos na conta; "
                       "as falas já geradas ficam guardadas.",
        "cota": f"A cota gratuita de hoje {de} acabou. Ela renova amanhã; "
                "as falas já geradas ficam guardadas.",
        "indisponivel": f"Não deu para conferir a chave {de} agora. Confira a internet.",
    }
    texto = textos[situacao]
    return f"{texto} ({detalhe})" if detalhe and situacao != "ok" else texto


class Registro:
    """Último erro de chave, crédito ou cota de cada provedor, em .cache/chaves.json."""

    def __init__(self, raiz: Path = Path("."), hoje: Callable[[], str] = lambda: date.today().isoformat()):
        self._arquivo = raiz / ".cache" / "chaves.json"
        self._hoje = hoje
        self._trava = threading.Lock()

    def _ler(self) -> dict:
        try:
            return json.loads(self._arquivo.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}

    def _gravar(self, dados: dict) -> None:
        self._arquivo.parent.mkdir(parents=True, exist_ok=True)
        self._arquivo.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")

    def anotar(self, provedor: str, motivo: str, detalhe: str) -> None:
        with self._trava:
            dados = self._ler()
            dados[provedor] = {"situacao": SITUACAO_DO_MOTIVO[motivo], "detalhe": detalhe, "dia": self._hoje(),
                               "chave": impressao(os.getenv(VARIAVEIS.get(provedor, "")))}
            self._gravar(dados)

    def limpar(self, provedor: str) -> None:
        with self._trava:
            dados = self._ler()
            if dados.pop(provedor, None) is not None:
                self._gravar(dados)

    def anotado(self, provedor: str) -> dict | None:
        """O erro anotado, se ainda vale para a chave atual (e, se for cota, para hoje)."""
        item = self._ler().get(provedor)
        if not item or item.get("chave") != impressao(os.getenv(VARIAVEIS.get(provedor, ""))):
            return None
        if item["situacao"] == "cota" and item.get("dia") != self._hoje():
            return None
        return item

    def vigiar(self, provedor: Provedor) -> "Vigiado":
        return Vigiado(provedor, self)


class Vigiado:
    """Provedor que anota no registro os erros de chave, crédito e cota, e esquece quando volta a sintetizar."""

    def __init__(self, provedor: Provedor, registro: Registro):
        self._provedor = provedor
        self._registro = registro
        self._limpo = False
        self.nome = provedor.nome

    def sintetizar(self, texto: str, voz: str, idioma: str) -> bytes:
        try:
            audio = self._provedor.sintetizar(texto, voz, idioma)
        except ErroTTS as e:
            if e.motivo in SITUACAO_DO_MOTIVO:
                self._registro.anotar(self.nome, e.motivo, str(e))
                self._limpo = False
            raise
        if not self._limpo:  # uma fala passou: o que estava anotado não vale mais
            self._registro.limpar(self.nome)
            self._limpo = True
        return audio


def conferir(provedor: Provedor) -> Verificacao:
    """Conferência online; provedor que não sabe se conferir conta como ok (a chave existe)."""
    return provedor.verificar() if hasattr(provedor, "verificar") else Verificacao("ok")


def situacao(nome: str, fabrica: Callable[[str], Provedor], registro: Registro,
             verificar: Callable[[Provedor], Verificacao] | None = None) -> dict:
    """Estado da chave de um provedor, juntando a conferência online (`verificar`, por padrão
    `conferir`) com o erro anotado."""
    try:
        provedor = fabrica(nome)
    except ErroConfig:
        sit, detalhe, saldo = "ausente", "", None
    else:
        v = (verificar or conferir)(provedor)
        sit, detalhe, saldo = v.situacao, v.detalhe, v.saldo
        anotado = registro.anotado(nome)
        if anotado and sit == "ok":
            # A conferência online desmente a chave recusada e, com saldo à vista, a falta de crédito.
            if anotado["situacao"] == "invalida" or (anotado["situacao"] == "sem_credito" and saldo is not None):
                registro.limpar(nome)
            else:
                sit, detalhe = anotado["situacao"], anotado["detalhe"]
        elif anotado and sit == "indisponivel":
            sit, detalhe = anotado["situacao"], anotado["detalhe"]
    return {
        "provedor": nome, "rotulo": ROTULOS.get(nome, nome), "variavel": VARIAVEIS.get(nome),
        "situacao": sit, "curto": CURTOS[sit], "mensagem": mensagem(nome, sit, detalhe),
        "bloqueia": sit in BLOQUEIAM, "saldo": saldo,
        "link_chave": LINKS_CHAVE.get(nome),
        "link_credito": LINKS_CREDITO.get(nome) if sit == "sem_credito" else None,
        "final": chave[-4:] if (chave := os.getenv(VARIAVEIS.get(nome, ""))) and sit != "ausente" else None,
    }
