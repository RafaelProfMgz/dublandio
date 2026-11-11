"""Uma etapa por vez em segundo plano, com um registro de eventos que o navegador acompanha."""

import threading
from collections.abc import Callable, Iterator

Emitir = Callable[[dict], None]


class Ocupado(Exception):
    """Já há uma etapa rodando."""


class Tarefas:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._eventos: list[dict] = []  # o id de cada evento é sua posição na lista
        self._rodando: dict | None = None
        self._thread: threading.Thread | None = None

    def estado(self) -> dict:
        with self._cond:
            return {"rodando": self._rodando, "proximo": len(self._eventos)}

    def iniciar(self, descricao: dict, trabalho: Callable[[Emitir], None]) -> int:
        """Roda `trabalho(emitir)` numa thread. Devolve o id do primeiro evento da tarefa."""
        with self._cond:
            if self._rodando is not None:
                raise Ocupado(f"já há uma etapa rodando: {self._rodando['etapa']} em {self._rodando['livro']}")
            self._rodando = descricao
            inicio = len(self._eventos)
            self._registrar({"tipo": "inicio", **descricao})
        self._thread = threading.Thread(target=self._executar, args=(trabalho,), daemon=True)
        self._thread.start()
        return inicio

    def emitir(self, evento: dict) -> None:
        with self._cond:
            self._registrar(evento)

    def aguardar(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def eventos(self, desde: int, espera: float = 15.0) -> Iterator[dict | None]:
        """Eventos a partir de `desde` até o fim da tarefa atual. `None` = nada novo (keepalive)."""
        while True:
            with self._cond:
                self._cond.wait_for(lambda: len(self._eventos) > desde or self._rodando is None, espera)
                novos = self._eventos[desde:]
                rodando = self._rodando is not None
            desde += len(novos)
            yield from novos
            if not rodando:  # o "fim" é registrado junto com rodando=None: já veio em `novos`
                return
            if not novos:
                yield None

    def _executar(self, trabalho: Callable[[Emitir], None]) -> None:
        ok = True
        try:
            trabalho(self.emitir)
        except Exception as e:  # a etapa falhou: o navegador precisa saber o porquê
            ok = False
            self.emitir({"tipo": "erro", "mensagem": str(e)})
        finally:
            with self._cond:
                descricao, self._rodando = self._rodando, None
                self._registrar({"tipo": "fim", "ok": ok, **(descricao or {})})

    def _registrar(self, evento: dict) -> None:
        self._eventos.append({"id": len(self._eventos), **evento})
        self._cond.notify_all()
