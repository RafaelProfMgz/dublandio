"""Contrato comum dos provedores de TTS."""

from dataclasses import dataclass
from typing import Protocol


class ErroTTS(Exception):
    """Falha ao sintetizar uma fala. `retentavel` indica se vale tentar de novo a mesma fala;
    `interromper`, que nenhuma outra fala vai passar (cota esgotada, chave inválida): para tudo.
    `motivo` diz o que a pessoa precisa resolver: "chave", "credito" ou "cota"."""

    def __init__(self, mensagem: str, retentavel: bool = False, interromper: bool = False, motivo: str | None = None):
        super().__init__(mensagem)
        self.retentavel = retentavel
        self.interromper = interromper
        self.motivo = motivo


class ErroConfig(Exception):
    """Configuração ausente ou inválida (ex.: chave de API não definida)."""


@dataclass
class Verificacao:
    """Resultado de conferir a chave no provedor, sem gastar crédito.
    `situacao`: ok, invalida, sem_credito ou indisponivel (não deu para conferir)."""

    situacao: str
    detalhe: str = ""
    saldo: float | None = None  # em dólares, quando o provedor informa


@dataclass
class Voz:
    """Uma voz do catálogo do provedor; `amostra` é a URL de um áudio de exemplo."""

    id: str
    nome: str
    idioma: str
    genero: str
    amostra: str | None = None


class Provedor(Protocol):
    nome: str

    def sintetizar(self, texto: str, voz: str, idioma: str) -> bytes:
        """Devolve o áudio da fala em WAV."""
        ...


def erro_http(status: int, mensagem: str) -> ErroTTS:
    # Limite de taxa e falhas do servidor costumam passar sozinhos; chave recusada (401/403) ou
    # sem crédito (402) não passa para fala nenhuma; o resto é erro desta fala.
    motivo = {401: "chave", 403: "chave", 402: "credito"}.get(status)
    return ErroTTS(f"HTTP {status}: {mensagem}", retentavel=status == 429 or status >= 500,
                   interromper=motivo is not None, motivo=motivo)
