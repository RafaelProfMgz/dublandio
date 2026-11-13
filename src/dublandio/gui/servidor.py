"""API da interface web + arquivos estáticos. Só escuta em 127.0.0.1 (veja `rodar`)."""

import json
import base64
import os
import threading
import time
import webbrowser
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dublandio import audio, avatares as avatares_livro, imagem_ia
from dublandio.chaves import ARTIGOS, ROTULOS, Registro, conferir, situacao
from dublandio.catalogo import IDIOMAS, carregar_catalogo
from dublandio.config import PROVEDORES, Livro, carregar_livro, definir_voz, ler_livro, livros_disponiveis, salvar_env
from dublandio.gui import status, videos
from dublandio.capitulo_hf import executar_capitulo, preparar_capitulo
from dublandio.gui.tarefas import Emitir, Ocupado, Tarefas
from dublandio.novo import criar_livro, importar_livro, parece_capitulo, textos_da_pasta
from dublandio.preparar import CAP, EXTENSOES, preparar_livro
from dublandio.roteiro import separar_livro
from dublandio.sintetizar import cadeia_do_livro, sintetizar_capitulo
from dublandio.tts import VARIAVEIS, ErroConfig, ErroTTS, Provedor, Verificacao, criar_provedor

ESTATICO = Path(__file__).parent / "estatico"
ETAPAS = ("preparar", "separar", "sintetizar")
CONFERIR_A_CADA = 300  # segundos entre conferências online da mesma chave


class Texto(BaseModel):
    texto: str


class EscolhaVoz(BaseModel):
    personagem: str = Field(min_length=1, max_length=200)
    voz: str = Field(min_length=1, max_length=300)
    provedor: str


class NovoLivro(BaseModel):
    titulo: str
    origem: str
    arquivos: list[str] = []
    provedor: str = "heygen"
    reserva: str | None = "openrouter"
    personagens: list[str] = []
    slug: str | None = None


class NovaChave(BaseModel):
    chave: str


class PedidoTarefa(BaseModel):
    etapa: str
    caps: list[str] | None = None


class ArquivoImportado(BaseModel):
    nome: str = Field(max_length=300)
    conteudo: str = Field(max_length=4_000_000)


class ImportacaoLivro(BaseModel):
    titulo: str
    arquivos: list[ArquivoImportado] = Field(min_length=1, max_length=500)
    provedor: str = 'heygen'
    reserva: str | None = 'openrouter'
    personagens: list[str] = Field(default_factory=list)


class FichaAvatar(BaseModel):
    personagem: str = Field(max_length=100)
    nome: str = Field('', max_length=200)
    descricao: str = Field('', max_length=2000)
    idade: str = Field('', max_length=50)
    voz: str = Field('', max_length=200)


class NovoAvatar(FichaAvatar):
    imagens: list[str] = Field(min_length=1, max_length=avatares_livro.MAX_IMAGENS)
    principal: int = 0


class PedidoIA(FichaAvatar):
    referencias: list[str] = Field(default_factory=list, max_length=avatares_livro.MAX_IMAGENS)
    ia: str = 'openai'


class EscolhaAvatar(BaseModel):
    avatar: str = Field(max_length=40)


class PedidoVideo(BaseModel):
    cap: str


def criar_app(
    raiz: Path = Path("."),
    fabrica_provedor: Callable[[str], Provedor] = criar_provedor,
    juntar: Callable[[list[Path], Path], None] = audio.concatenar,
    espera: float = 1.0,
    raiz_pastas: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="dublandio", docs_url=None, redoc_url=None)
    tarefas = Tarefas()
    app.state.tarefas = tarefas
    registro = Registro(raiz)
    conferidas: dict[str, tuple[float, Verificacao]] = {}  # provedor -> (quando, resultado)
    # "Adicionar livro" só navega dentro desta pasta (a pessoal, por padrão).
    raiz_pastas = (raiz_pastas or Path.home()).resolve()

    def pasta_permitida(caminho: str | None) -> Path:
        if not caminho:
            livros = raiz_pastas / "Documentos" / "livros"
            return livros if livros.is_dir() else raiz_pastas
        pasta = Path(caminho).expanduser().resolve()
        if not pasta.is_relative_to(raiz_pastas):
            raise HTTPException(403, f"só dá para escolher pastas dentro de {raiz_pastas}")
        if not pasta.is_dir():
            raise HTTPException(404, f"pasta não existe: {pasta}")
        return pasta

    def livro(slug: str) -> Livro:
        if slug not in livros_disponiveis(raiz):  # também barra "../" no slug
            raise HTTPException(404, f"livro '{slug}' não encontrado")
        try:
            return carregar_livro(slug, raiz)
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e)) from e

    def cap_valido(cap: str) -> str:
        if not status.CAP.fullmatch(cap):
            raise HTTPException(400, f"capítulo inválido: '{cap}' (use cap_NNN)")
        return cap

    def separar_com_aviso(lv: Livro) -> str | None:
        """`separar` depois de salvar; um erro aqui vira aviso, o arquivo já foi salvo."""
        try:
            separar_livro(lv)
        except (ValueError, KeyError) as e:
            return f"salvo, mas o separar falhou: {e}"
        return None

    @app.get("/api/livros")
    def listar() -> list[dict]:
        resultado = []
        for slug in livros_disponiveis(raiz):
            try:
                resultado.append(status.resumo_livro(carregar_livro(slug, raiz)))
            except (ValueError, KeyError) as e:
                resultado.append({"slug": slug, "titulo": slug, "erro": str(e)})
        return resultado

    @app.get("/api/livros/{slug}")
    def detalhar(slug: str) -> dict:
        lv = livro(slug)
        return {
            **status.resumo_livro(lv),
            "lista": [status.status_capitulo(lv, c) for c in status.capitulos(lv)],
            "vozes": status.vozes(lv),
            "reserva": lv.reserva,
            "idioma": lv.idioma,
            "idioma_catalogo": IDIOMAS.get(lv.idioma, lv.idioma),
            # Como está no livro.yaml: personagem -> voz, no provedor do livro.
            "mapa_vozes": lv.vozes.get(lv.provedor, {}),
        }

    @app.get("/api/catalogo/{provedor}")
    def catalogo(provedor: str, atualizar: bool = False) -> dict:
        try:
            vozes, buscado_em = carregar_catalogo(provedor, fabrica_provedor, raiz, atualizar=atualizar)
        except ErroConfig as e:
            raise HTTPException(400, str(e)) from e
        except ErroTTS as e:
            raise HTTPException(502, f"a {provedor} não respondeu: {e}") from e
        return {"vozes": [asdict(v) for v in vozes], "buscado_em": buscado_em}

    @app.get("/api/chaves")
    def chaves(atualizar: bool = False) -> list[dict]:
        def conferir_com_cache(nome: str) -> Callable[[Provedor], Verificacao]:
            def conferir_nome(provedor: Provedor) -> Verificacao:
                antes = conferidas.get(nome)
                if antes and not atualizar and time.monotonic() - antes[0] < CONFERIR_A_CADA:
                    return antes[1]
                v = conferir(provedor)
                conferidas[nome] = (time.monotonic(), v)
                return v
            return conferir_nome

        return [situacao(nome, fabrica_provedor, registro, conferir_com_cache(nome)) for nome in PROVEDORES]

    @app.put("/api/chaves/{provedor}")
    def salvar_chave(provedor: str, corpo: NovaChave) -> dict:
        """Confere a chave colada e, se o provedor não recusar, grava no .env e passa a usá-la já."""
        if provedor in imagem_ia.VARIAVEIS:
            valor = corpo.chave.strip().strip('"').strip("'")
            if not valor or len(valor) > 500 or any(c.isspace() for c in valor):
                raise HTTPException(400, "cole só a chave, sem espaços nem quebras de linha")
            try:
                imagem_ia.validar_chave(provedor, valor)
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
            except imagem_ia.ErroIA as e:
                raise HTTPException(502, str(e)) from e
            salvar_env(raiz / '.env', imagem_ia.VARIAVEIS[provedor], valor)
            return imagem_ia.situacao()[provedor]
        if provedor not in VARIAVEIS and provedor != 'huggingface':
            raise HTTPException(404, f"provedor desconhecido: {provedor}")
        valor = corpo.chave.strip().strip('"').strip("'")
        if not valor or len(valor) > 500 or any(c.isspace() for c in valor):
            raise HTTPException(400, "cole só a chave, sem espaços nem quebras de linha")
        if provedor == 'huggingface':
            try:
                videos.validar_token_hf(valor)
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
            except Exception as e:
                raise HTTPException(502, 'Não foi possível conferir o token no Hugging Face. Tente novamente.') from e
            salvar_env(raiz / '.env', 'HF_TOKEN', valor)
            return videos.chave_hf()
        variavel, rotulo = VARIAVEIS[provedor], ROTULOS.get(provedor, provedor)
        anterior = os.environ.get(variavel)
        os.environ[variavel] = valor  # a fábrica lê a chave do ambiente
        try:
            v = conferir(fabrica_provedor(provedor))
        except ErroConfig as e:
            v = Verificacao("invalida", str(e))
        if v.situacao == "invalida":
            if anterior is None:
                os.environ.pop(variavel, None)
            else:
                os.environ[variavel] = anterior
            artigo = ARTIGOS.get(provedor, "o").upper()
            raise HTTPException(400, f"{artigo} {rotulo} recusou essa chave; nada foi salvo. Confira se copiou a chave inteira.")
        salvar_env(raiz / ".env", variavel, valor)
        conferidas[provedor] = (time.monotonic(), v)
        return situacao(provedor, fabrica_provedor, registro, lambda _: v)

    @app.get("/api/pastas")
    def pastas(caminho: str | None = None) -> dict:
        pasta = pasta_permitida(caminho)
        try:
            itens = sorted((p for p in pasta.iterdir() if not p.name.startswith(".")), key=lambda p: p.name.lower())
        except PermissionError as e:
            raise HTTPException(403, f"sem permissão para ler {pasta}") from e
        return {
            "caminho": str(pasta),
            "pai": str(pasta.parent) if pasta != raiz_pastas else None,
            "pastas": [{"nome": p.name, "caminho": str(p)} for p in itens if p.is_dir()],
            "textos": sum(p.suffix in EXTENSOES for p in itens if p.is_file()),
        }

    @app.get("/api/pastas/textos")
    def textos(caminho: str) -> dict:
        pasta = pasta_permitida(caminho)
        arquivos = textos_da_pasta(pasta)
        return {
            "caminho": str(pasta),
            "nome": pasta.name,
            # Pasta no padrão cap_NNN: os capítulos já estão nomeados e em ordem.
            "padrao": any("/" not in a and CAP.fullmatch(Path(a).stem) for a in arquivos),
            "arquivos": [{"caminho": a, "sugerido": parece_capitulo(a)} for a in arquivos],
        }

    @app.post("/api/livros")
    def adicionar(pedido: NovoLivro) -> dict:
        origem = pasta_permitida(pedido.origem)
        try:
            lv = criar_livro(raiz, pedido.titulo, origem, pedido.arquivos, provedor=pedido.provedor,
                             reserva=pedido.reserva, personagens=pedido.personagens, slug=pedido.slug)
        except (ValueError, FileNotFoundError) as e:
            raise HTTPException(400, str(e)) from e

        return preparar_adicionado(lv)

    def preparar_adicionado(lv: Livro) -> dict:
        def trabalho(emitir: Emitir) -> None:
            emitir({"tipo": "log", "mensagem": f"{len(preparar_livro(lv))} roteiro(s) criado(s)"})
            emitir({"tipo": "log", "mensagem": f"{len(separar_livro(lv))} manifesto(s) gerado(s)"})

        try:
            desde = tarefas.iniciar({"livro": lv.slug, "etapa": "preparar", "caps": []}, trabalho)
        except Ocupado as e:  # o livro foi criado; os roteiros ficam para depois
            return {"slug": lv.slug, "desde": None, "aviso": f"livro criado, mas {e}. Rode Preparar roteiros depois."}
        return {"slug": lv.slug, "desde": desde, "aviso": None}

    @app.post('/api/livros/importar')
    def importar(pedido: ImportacaoLivro) -> dict:
        try:
            arquivos = [(a.nome, base64.b64decode(a.conteudo, validate=True)) for a in pedido.arquivos]
            if sum(len(conteudo) for _, conteudo in arquivos) > 30_000_000:
                raise ValueError('importe até 30 MB de capítulos por vez')
            lv = importar_livro(raiz, pedido.titulo, arquivos, provedor=pedido.provedor,
                                reserva=pedido.reserva, personagens=pedido.personagens)
        except (ValueError, FileNotFoundError, FileExistsError) as e:
            raise HTTPException(400, str(e)) from e
        return preparar_adicionado(lv)

    @app.get('/api/video/huggingface')
    def chave_video(atualizar: bool = False) -> dict:
        return videos.chave_hf(atualizar)

    @app.get('/api/livros/{slug}/videos')
    def listar_videos(slug: str) -> dict:
        lv = livro(slug)
        lista = []
        for cap in status.capitulos(lv):
            p = videos.progresso(lv, cap)
            tem_audio = (lv.dir_audio / f'{cap}.wav').is_file()
            aviso = None
            if tem_audio and not p.get('avatar_unico') and not p['segundos']:
                try:
                    avatares_livro.segmentos(lv, cap)
                except (ValueError, OSError) as e:
                    aviso = str(e)
            lista.append({'cap': cap, 'tem_audio': tem_audio, 'aviso': aviso,
                          'personagens': avatares_livro.personagens_do_capitulo(lv, cap), **p})
        donos = {a['personagem']: a['id'] for a in avatares_livro.listar(lv) if a['personagem']}
        return {'avatares': [{k: v for k, v in a.items() if k != 'caminho'} for a in avatares_livro.listar(lv)],
                'personagens': [{'personagem': n, 'avatar': donos.get(n), 'voz': avatares_livro.voz_do_personagem(lv, n)}
                                for n in avatares_livro.personagens(lv)],
                'capitulos': lista, 'hf': videos.chave_hf(), 'ia': imagem_ia.situacao()}

    def imagens_b64(lista: list[str]) -> list[bytes]:
        try:
            return [base64.b64decode(x, validate=True) for x in lista]
        except ValueError as e:
            raise HTTPException(400, 'uma das imagens não foi enviada corretamente') from e

    @app.post('/api/livros/{slug}/videos/avatares')
    def criar_avatar(slug: str, pedido: NovoAvatar) -> dict:
        try:
            f = avatares_livro.criar(livro(slug), pedido.personagem, imagens_b64(pedido.imagens), pedido.principal,
                                     nome=pedido.nome, descricao=pedido.descricao, idade=pedido.idade, voz=pedido.voz)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return f

    def chamar_ia(funcao, *args):
        try:
            return funcao(*args)
        except imagem_ia.ErroIA as e:
            raise HTTPException(400, str(e)) from e

    @app.post('/api/livros/{slug}/videos/avatares/descrever')
    def descrever_avatar(slug: str, pedido: PedidoIA) -> dict:
        livro(slug)
        texto = chamar_ia(imagem_ia.descrever, pedido.model_dump(), imagens_b64(pedido.referencias), pedido.ia)
        return {'descricao': texto}

    @app.post('/api/livros/{slug}/videos/avatares/imagem-ia')
    def imagem_com_ia(slug: str, pedido: PedidoIA) -> dict:
        livro(slug)
        png, texto = chamar_ia(imagem_ia.criar_imagem, pedido.model_dump(), imagens_b64(pedido.referencias), pedido.ia)
        return {'conteudo': base64.b64encode(png).decode(), 'pedido': texto}

    @app.get('/api/livros/{slug}/videos/imagens/{arquivo}')
    def imagem_do_livro(slug: str, arquivo: str) -> FileResponse:
        path = avatares_livro.imagem(livro(slug), arquivo)
        if path is None:
            raise HTTPException(404, 'imagem não encontrada')
        return FileResponse(path, headers={'X-Content-Type-Options': 'nosniff'})

    @app.put('/api/livros/{slug}/videos/personagens/{personagem}')
    def escolher_avatar(slug: str, personagem: str, pedido: EscolhaAvatar) -> dict:
        try:
            return avatares_livro.atribuir(livro(slug), personagem, pedido.avatar)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @app.get('/api/livros/{slug}/videos/avatares/{identificador}')
    def imagem_avatar(slug: str, identificador: str) -> FileResponse:
        imagem = avatares_livro.caminho(livro(slug), identificador)
        if imagem is None:
            raise HTTPException(404, 'avatar não encontrado')
        return FileResponse(imagem, headers={'X-Content-Type-Options': 'nosniff'})

    @app.get('/api/livros/{slug}/videos/{cap}/arquivo')
    def assistir_video(slug: str, cap: str, parcial: bool = False) -> FileResponse:
        arquivo = livro(slug).dir / 'video' / f"{cap_valido(cap)}-hf{'-parcial' if parcial else ''}.mp4"
        if not arquivo.is_file():
            raise HTTPException(404, 'este vídeo ainda não está pronto')
        return FileResponse(arquivo, media_type='video/mp4')

    @app.post('/api/livros/{slug}/videos/tarefas')
    def gerar_video(slug: str, pedido: PedidoVideo) -> dict:
        lv = livro(slug)
        cap = cap_valido(pedido.cap)
        if not os.getenv('HF_TOKEN'):
            raise HTTPException(400, 'Configure o token do Hugging Face na aba Vídeos.')
        try:
            preparar_capitulo(lv, int(cap[4:]))
        except (ValueError, OSError) as e:
            raise HTTPException(400, str(e)) from e

        def trabalho(emitir: Emitir) -> None:
            def atualizar(mensagem=None):
                if mensagem:
                    emitir({'tipo': 'log', 'mensagem': mensagem})
                p = videos.progresso(lv, cap)
                emitir({'tipo': 'video_progresso', 'cap': cap, 'segundos': p['segundos'],
                        'total': p['total'], 'situacao': p['situacao']})
            atualizar()
            executar_capitulo(lv, int(cap[4:]), os.environ['HF_TOKEN'], ao_progredir=atualizar)
            atualizar()
            p = videos.progresso(lv, cap)
            if p['situacao'] == 'aguardando_cota':
                emitir({'tipo': 'log', 'mensagem': 'Limite gratuito atingido. Trechos salvos; retome após a renovação.'})
        try:
            desde = tarefas.iniciar({'livro': slug, 'etapa': 'video', 'caps': [cap]}, trabalho)
        except Ocupado as e:
            raise HTTPException(409, str(e)) from e
        return {'desde': desde}

    @app.get("/api/livros/{slug}/roteiro/{cap}")
    def ler_roteiro(slug: str, cap: str) -> dict:
        arquivo = livro(slug).dir_roteiro / f"{cap_valido(cap)}.txt"
        if not arquivo.exists():
            raise HTTPException(404, f"{cap} não tem roteiro (rode preparar)")
        return {"texto": arquivo.read_text(encoding="utf-8")}

    @app.put("/api/livros/{slug}/roteiro/{cap}")
    def salvar_roteiro(slug: str, cap: str, corpo: Texto) -> dict:
        lv = livro(slug)
        arquivo = lv.dir_roteiro / f"{cap_valido(cap)}.txt"
        if not arquivo.exists():
            raise HTTPException(404, f"{cap} não tem roteiro (rode preparar)")
        arquivo.write_text(corpo.texto, encoding="utf-8")
        return {"aviso": separar_com_aviso(lv), "status": status.status_capitulo(lv, cap)}

    @app.get("/api/livros/{slug}/config")
    def ler_config(slug: str) -> dict:
        return {"texto": (livro(slug).dir / "livro.yaml").read_text(encoding="utf-8")}

    @app.put("/api/livros/{slug}/voz")
    def escolher_voz(slug: str, corpo: EscolhaVoz) -> dict:
        lv = livro(slug)
        if corpo.provedor != lv.provedor:
            raise HTTPException(409, "O provedor do livro mudou. Abra o seletor novamente.")
        if tarefas.estado()["rodando"]:
            raise HTTPException(409, "Espere a etapa atual terminar antes de trocar uma voz.")
        personagem = lv.nome_canonico(corpo.personagem.strip())
        voz = corpo.voz.strip()
        conhecidos = {"Narrador", *lv.personagens, *lv.vozes.get(lv.provedor, {}),
                      *(v["personagem"] for v in status.vozes(lv))}
        if personagem not in conhecidos or not voz:
            raise HTTPException(400, "Personagem ou voz inválidos.")
        arquivo = lv.dir / "livro.yaml"
        try:
            texto = definir_voz(arquivo.read_text(encoding="utf-8"), lv.provedor, personagem, voz)
            novo = ler_livro(texto, slug, raiz)
        except (ValueError, yaml.YAMLError) as e:
            raise HTTPException(400, str(e)) from e
        arquivo.write_text(texto, encoding="utf-8")
        return {"aviso": separar_com_aviso(novo)}

    @app.put("/api/livros/{slug}/config")
    def salvar_config(slug: str, corpo: Texto) -> dict:
        lv = livro(slug)
        try:
            novo = ler_livro(corpo.texto, slug, raiz)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        (lv.dir / "livro.yaml").write_text(corpo.texto, encoding="utf-8")
        return {"aviso": separar_com_aviso(novo)}

    @app.get("/api/livros/{slug}/audio/{cap}")
    def ouvir(slug: str, cap: str) -> FileResponse:
        arquivo = livro(slug).dir_audio / f"{cap_valido(cap)}.wav"
        if not arquivo.exists():
            raise HTTPException(404, f"{cap} ainda não tem áudio")
        return FileResponse(arquivo, media_type="audio/wav")

    @app.post("/api/livros/{slug}/tarefas")
    def iniciar(slug: str, pedido: PedidoTarefa) -> dict:
        lv = livro(slug)
        if pedido.etapa not in ETAPAS:
            raise HTTPException(400, f"etapa inválida: '{pedido.etapa}' (use {', '.join(ETAPAS)})")
        caps = [cap_valido(c) for c in pedido.caps or []]

        if pedido.etapa == "preparar":
            def trabalho(emitir: Emitir) -> None:
                # Sem --forcar, nunca: os roteiros são editados à mão.
                escritos = preparar_livro(lv)
                emitir({"tipo": "log", "mensagem": f"{len(escritos)} roteiro(s) novo(s); os existentes foram mantidos"})
        elif pedido.etapa == "separar":
            def trabalho(emitir: Emitir) -> None:
                emitir({"tipo": "log", "mensagem": f"{len(separar_livro(lv))} manifesto(s) gerado(s)"})
        else:
            try:  # chave ausente vira erro já na resposta, não depois
                # Vigiado: erros de chave, crédito e cota ficam anotados para o alerta da interface.
                cadeia, avisos = cadeia_do_livro(lv, lambda nome: registro.vigiar(fabrica_provedor(nome)))
            except ErroConfig as e:
                raise HTTPException(400, str(e)) from e
            manifestos = sorted(lv.dir_manifesto.glob("cap_*.json"))
            if caps:
                manifestos = [m for m in manifestos if m.stem in caps]
            if not manifestos:
                raise HTTPException(400, "nenhum manifesto para sintetizar (rode separar)")

            def trabalho(emitir: Emitir) -> None:
                # Um ErroTTS com `interromper`, sem reserva que sobre, sobe daqui: a tarefa termina com "erro" + "fim".
                for aviso in avisos:
                    emitir({"tipo": "log", "mensagem": aviso})
                for m in manifestos:
                    cap = m.stem
                    emitir({"tipo": "capitulo_inicio", "cap": cap})
                    r = sintetizar_capitulo(
                        lv, m, cadeia, espera=espera, juntar=juntar,
                        ao_trocar=lambda de, para, motivo: emitir({"tipo": "troca", "de": de, "para": para, "motivo": motivo}),
                        ao_progredir=lambda fala, estado, cap=cap: emitir(
                            {"tipo": "fala", "cap": cap, "ordem": fala.ordem,
                             "personagem": fala.personagem, "ok": estado == "ok", "estado": estado}),
                    )
                    emitir({
                        "tipo": "capitulo", "cap": cap, "geradas": r.geradas, "reusadas": r.reusadas,
                        "montado": r.arquivo is not None,
                        "falhas": [{"ordem": f.ordem, "personagem": f.personagem, "erro": e} for f, e in r.falhas],
                    })

        try:
            inicio = tarefas.iniciar({"livro": slug, "etapa": pedido.etapa, "caps": caps}, trabalho)
        except Ocupado as e:
            raise HTTPException(409, str(e)) from e
        return {"desde": inicio}

    @app.get("/api/tarefas")
    def estado() -> dict:
        return tarefas.estado()

    @app.get("/api/tarefas/eventos")
    def eventos(request: Request, desde: int = 0) -> StreamingResponse:
        ultimo = request.headers.get("last-event-id")
        if ultimo and ultimo.isdigit():  # reconexão do EventSource
            desde = max(desde, int(ultimo) + 1)

        def stream():
            for e in tarefas.eventos(desde):
                if e is None:
                    yield ": ainda rodando\n\n"
                else:
                    yield f"id: {e['id']}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.middleware("http")
    async def sem_cache_velho(request: Request, chamar_proximo):
        # Revalida sempre (via ETag): depois de atualizar o dublandio, o navegador não usa o app.js antigo.
        resposta = await chamar_proximo(request)
        resposta.headers.setdefault("Cache-Control", "no-cache")
        return resposta

    app.mount("/", StaticFiles(directory=ESTATICO, html=True), name="estatico")
    return app


def rodar(porta: int = 8765, abrir: bool = True, host: str = "127.0.0.1") -> None:
    import uvicorn

    url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{porta}"
    print(f"dublandio rodando em {url} (Ctrl+C para sair)")
    if abrir:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(criar_app(), host=host, port=porta, log_level="warning")
