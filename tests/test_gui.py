import json

import pytest
from fastapi.testclient import TestClient

from dublandio.gui.servidor import criar_app
from dublandio.gui.tarefas import Ocupado, Tarefas
from dublandio.tts import ErroConfig, ErroTTS

YAML = "titulo: Ex\nprovedor: heygen\n# comentário mantido\napelidos: {Ele: Fonoti}\nvozes:\n  heygen: {Narrador: N, Fonoti: X}\n"


class Falso:
    nome = "heygen"

    def __init__(self, falhar: set[str] = frozenset()):
        self.falhar = falhar
        self.textos: list[str] = []

    def sintetizar(self, texto, voz, idioma):
        if texto in self.falhar:
            raise ErroTTS("recusado")
        self.textos.append(texto)
        return b"RIFF" + texto.encode()


def juntar_falso(partes, destino):
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(b"".join(p.read_bytes() for p in partes))


@pytest.fixture
def projeto(tmp_path):
    pasta = tmp_path / "livros" / "ex"
    (pasta / "roteiro").mkdir(parents=True)
    (pasta / "livro.yaml").write_text(YAML, encoding="utf-8")
    (pasta / "roteiro" / "cap_001.txt").write_text("Ele: Oi.\n\nKamille: Tchau.\n\nA porta bateu.", encoding="utf-8")
    return tmp_path


@pytest.fixture
def provedor():
    return Falso()


@pytest.fixture
def cliente(projeto, provedor):
    app = criar_app(projeto, fabrica_provedor=lambda nome: provedor, juntar=juntar_falso, espera=0)
    with TestClient(app) as c:
        c.tarefas = app.state.tarefas
        yield c


def rodar(cliente, etapa, caps=None):
    r = cliente.post("/api/livros/ex/tarefas", json={"etapa": etapa, "caps": caps})
    assert r.status_code == 200, r.text
    cliente.tarefas.aguardar(5)
    return r.json()["desde"]


def eventos(cliente, desde):
    corpo = cliente.get(f"/api/tarefas/eventos?desde={desde}").text
    return [json.loads(l[6:]) for l in corpo.splitlines() if l.startswith("data: ")]


def test_lista_livros(cliente):
    assert cliente.get("/api/livros").json() == [
        {"slug": "ex", "titulo": "Ex", "provedor": "heygen", "tem_origem": False, "capitulos": 1, "com_audio": 0}
    ]


def test_livro_inexistente(cliente):
    assert cliente.get("/api/livros/nao-existe").status_code == 404
    assert cliente.get("/api/livros/roteiro").status_code == 404  # pasta que não é livro


def test_detalhe_antes_de_separar(cliente):
    cap = cliente.get("/api/livros/ex").json()["lista"][0]
    assert cap["cap"] == "cap_001" and cap["tem_roteiro"] and not cap["tem_manifesto"]
    assert cap["falas"] == [] and cap["pendentes"] == 0


def test_separar_e_vozes(cliente):
    eventos_tarefa = eventos(cliente, rodar(cliente, "separar"))
    assert [e["tipo"] for e in eventos_tarefa] == ["inicio", "log", "fim"]
    assert eventos_tarefa[-1]["ok"] is True

    livro = cliente.get("/api/livros/ex").json()
    cap = livro["lista"][0]
    assert [f["personagem"] for f in cap["falas"]] == ["Fonoti", "Kamille", "Narrador"]
    assert cap["pendentes"] == 3
    kamille = next(v for v in livro["vozes"] if v["personagem"] == "Kamille")
    assert kamille == {"personagem": "Kamille", "falas": 1, "voz": "N", "voz_propria": False}


def test_sintetizar_monta_audio_e_usa_cache(cliente, provedor, projeto):
    rodar(cliente, "separar")
    evs = eventos(cliente, rodar(cliente, "sintetizar", ["cap_001"]))
    assert [e["tipo"] for e in evs].count("fala") == 3
    capitulo = next(e for e in evs if e["tipo"] == "capitulo")
    assert capitulo["montado"] and capitulo["geradas"] == 3 and capitulo["falhas"] == []

    cap = cliente.get("/api/livros/ex").json()["lista"][0]
    assert cap["tem_audio"] and cap["pendentes"] == 0
    r = cliente.get("/api/livros/ex/audio/cap_001")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"

    rodar(cliente, "sintetizar")  # tudo em cache: nada novo vai ao provedor
    assert len(provedor.textos) == 3


def test_sintetizar_com_falha_nao_monta(cliente, provedor):
    provedor.falhar = {"Tchau."}
    rodar(cliente, "separar")
    evs = eventos(cliente, rodar(cliente, "sintetizar"))
    capitulo = next(e for e in evs if e["tipo"] == "capitulo")
    assert not capitulo["montado"]
    assert capitulo["falhas"] == [{"ordem": 2, "personagem": "Kamille", "erro": "recusado"}]
    assert cliente.get("/api/livros/ex").json()["lista"][0]["pendentes"] == 1


def test_sintetizar_sem_chave_responde_400(projeto):
    def sem_chave(nome):
        raise ErroConfig("defina HEYGEN_API_KEY")

    with TestClient(criar_app(projeto, fabrica_provedor=sem_chave)) as c:
        c.post("/api/livros/ex/tarefas", json={"etapa": "separar"})
        c.app.state.tarefas.aguardar(5)
        r = c.post("/api/livros/ex/tarefas", json={"etapa": "sintetizar"})
    assert r.status_code == 400 and "HEYGEN_API_KEY" in r.json()["detail"]


def test_sintetizar_sem_manifesto_responde_400(cliente):
    r = cliente.post("/api/livros/ex/tarefas", json={"etapa": "sintetizar"})
    assert r.status_code == 400 and "separar" in r.json()["detail"]


def test_etapa_e_capitulo_invalidos(cliente):
    assert cliente.post("/api/livros/ex/tarefas", json={"etapa": "apagar"}).status_code == 400
    assert cliente.post("/api/livros/ex/tarefas", json={"etapa": "separar", "caps": ["../x"]}).status_code == 400
    assert cliente.get("/api/livros/ex/roteiro/..%2Flivro").status_code in (400, 404)


def test_preparar_sem_origem_vira_erro_no_evento(cliente):
    evs = eventos(cliente, rodar(cliente, "preparar"))
    assert evs[-2]["tipo"] == "erro" and "origem" in evs[-2]["mensagem"]
    assert evs[-1] == {**evs[-1], "tipo": "fim", "ok": False}


def test_salvar_roteiro_separa_de_novo(cliente):
    assert cliente.get("/api/livros/ex/roteiro/cap_001").json()["texto"].startswith("Ele: Oi.")
    r = cliente.put("/api/livros/ex/roteiro/cap_001", json={"texto": "Fonoti: Só isso."})
    assert r.status_code == 200 and r.json()["aviso"] is None
    assert [f["personagem"] for f in r.json()["status"]["falas"]] == ["Fonoti"]


def test_salvar_roteiro_inexistente_responde_404(cliente):
    assert cliente.put("/api/livros/ex/roteiro/cap_009", json={"texto": "x"}).status_code == 404


def test_config_preserva_comentarios(cliente, projeto):
    assert "# comentário mantido" in cliente.get("/api/livros/ex/config").json()["texto"]
    novo = YAML.replace("Fonoti: X", "Fonoti: X, Kamille: K")
    assert cliente.put("/api/livros/ex/config", json={"texto": novo}).status_code == 200
    assert (projeto / "livros" / "ex" / "livro.yaml").read_text(encoding="utf-8") == novo
    kamille = next(v for v in cliente.get("/api/livros/ex").json()["vozes"] if v["personagem"] == "Kamille")
    assert kamille["voz"] == "K" and kamille["voz_propria"]


def test_config_invalida_nao_grava(cliente, projeto):
    r = cliente.put("/api/livros/ex/config", json={"texto": "provedor: nenhum\n"})
    assert r.status_code == 400 and "provedor inválido" in r.json()["detail"]
    assert (projeto / "livros" / "ex" / "livro.yaml").read_text(encoding="utf-8") == YAML


def test_config_sem_narrador_salva_com_aviso(cliente):
    r = cliente.put("/api/livros/ex/config", json={"texto": "titulo: Ex\nprovedor: heygen\n"})
    assert r.status_code == 200 and "separar falhou" in r.json()["aviso"]


def test_pagina_inicial(cliente):
    r = cliente.get("/")
    assert r.status_code == 200 and "app.js" in r.text


def test_tarefas_uma_por_vez():
    import threading

    tarefas, liberar = Tarefas(), threading.Event()
    tarefas.iniciar({"livro": "ex", "etapa": "separar"}, lambda emitir: liberar.wait(5))
    with pytest.raises(Ocupado):
        tarefas.iniciar({"livro": "ex", "etapa": "separar"}, lambda emitir: None)
    liberar.set()
    tarefas.aguardar(5)
    assert tarefas.estado() == {"rodando": None, "proximo": 2}
    assert [e["tipo"] for e in tarefas.eventos(0) if e] == ["inicio", "fim"]


def test_estaticos_sempre_revalidados(cliente):
    assert cliente.get("/app.js").headers["cache-control"] == "no-cache"


def test_catalogo_e_mapa_de_vozes(projeto):
    from dublandio.tts import Voz

    class ComLista(Falso):
        def listar_vozes(self):
            return [Voz("X", "Yuri", "Portuguese", "male", "https://x/y.mp3")]

    with TestClient(criar_app(projeto, fabrica_provedor=lambda nome: ComLista())) as c:
        r = c.get("/api/catalogo/heygen")
        livro = c.get("/api/livros/ex").json()
    assert r.status_code == 200
    assert r.json()["vozes"] == [{"id": "X", "nome": "Yuri", "idioma": "Portuguese", "genero": "male", "amostra": "https://x/y.mp3", "idade": "", "sotaque": "", "descricao": ""}]
    assert livro["mapa_vozes"] == {"Narrador": "N", "Fonoti": "X"}
    assert livro["idioma_catalogo"] == "Portuguese"


def test_catalogo_provedor_sem_lista_responde_400(cliente):
    r = cliente.get("/api/catalogo/heygen")  # o Falso só sintetiza
    assert r.status_code == 400 and "não publica" in r.json()["detail"]


def test_catalogo_provedor_fora_do_ar_responde_502(projeto):
    class Fora(Falso):
        def listar_vozes(self):
            raise ErroTTS("HTTP 503: indisponível")

    with TestClient(criar_app(projeto, fabrica_provedor=lambda nome: Fora())) as c:
        r = c.get("/api/catalogo/heygen")
    assert r.status_code == 502 and "503" in r.json()["detail"]


def test_sintetizar_troca_para_reserva_e_avisa(projeto):
    arquivo = projeto / "livros" / "ex" / "livro.yaml"
    arquivo.write_text(YAML.replace("provedor: heygen\n", "provedor: heygen\nreserva: openrouter\n")
                       + "  openrouter: {Narrador: lucian}\n", encoding="utf-8")

    class SemCota(Falso):
        def sintetizar(self, texto, voz, idioma):
            raise ErroTTS("cota diária acabou", interromper=True)

    reserva = Falso()
    reserva.nome = "openrouter"
    provedores = {"heygen": SemCota(), "openrouter": reserva}
    app = criar_app(projeto, fabrica_provedor=provedores.__getitem__, juntar=juntar_falso, espera=0)
    with TestClient(app) as c:
        c.tarefas = app.state.tarefas
        assert c.get("/api/livros/ex").json()["reserva"] == "openrouter"
        rodar(c, "separar")
        evs = eventos(c, rodar(c, "sintetizar"))
        cap = c.get("/api/livros/ex").json()["lista"][0]

    trocas = [(e["de"], e["para"], e["motivo"]) for e in evs if e["tipo"] == "troca"]
    assert trocas == [("heygen", "openrouter", "cota diária acabou")]
    assert next(e for e in evs if e["tipo"] == "capitulo")["montado"]
    assert evs[-1]["ok"] is True
    assert cap["pendentes"] == 0 and cap["tem_audio"]  # o que a reserva gerou conta como pronto


def test_sintetizar_sem_reserva_interrompe_com_erro(projeto):
    class SemCota(Falso):
        def sintetizar(self, texto, voz, idioma):
            raise ErroTTS("cota diária acabou", interromper=True)

    app = criar_app(projeto, fabrica_provedor=lambda nome: SemCota(), juntar=juntar_falso, espera=0)
    with TestClient(app) as c:
        c.tarefas = app.state.tarefas
        rodar(c, "separar")
        evs = eventos(c, rodar(c, "sintetizar"))
    assert [e["tipo"] for e in evs][-3:] == ["fala", "erro", "fim"]
    assert "cota" in evs[-2]["mensagem"] and evs[-1]["ok"] is False


@pytest.fixture
def com_pastas(projeto):
    casa = projeto / "casa"
    (casa / "Documentos" / "livros" / "meu_livro" / "vol1").mkdir(parents=True)
    vol = casa / "Documentos" / "livros" / "meu_livro" / "vol1"
    (vol / "cap_001.md").write_text("— Oi. — disse Ana.\n\nA porta bateu.", encoding="utf-8")
    (vol / "README.md").write_text("notas", encoding="utf-8")
    app = criar_app(projeto, fabrica_provedor=lambda nome: Falso(), juntar=juntar_falso, espera=0, raiz_pastas=casa)
    with TestClient(app) as c:
        c.tarefas = app.state.tarefas
        c.casa = casa
        yield c


def test_pastas_comeca_em_documentos_livros(com_pastas):
    r = com_pastas.get("/api/pastas").json()
    assert r["caminho"].endswith("Documentos/livros") and [p["nome"] for p in r["pastas"]] == ["meu_livro"]
    vol = com_pastas.get("/api/pastas", params={"caminho": str(com_pastas.casa / "Documentos/livros/meu_livro/vol1")}).json()
    assert vol["textos"] == 2 and vol["pai"].endswith("meu_livro")
    assert com_pastas.get("/api/pastas", params={"caminho": str(com_pastas.casa)}).json()["pai"] is None


def test_pastas_fora_da_casa_e_proibido(com_pastas):
    assert com_pastas.get("/api/pastas", params={"caminho": "/etc"}).status_code == 403
    assert com_pastas.get("/api/pastas", params={"caminho": str(com_pastas.casa / "..")}).status_code == 403


def test_textos_da_pasta_marca_sugeridos(com_pastas):
    r = com_pastas.get("/api/pastas/textos", params={"caminho": str(com_pastas.casa / "Documentos/livros/meu_livro/vol1")}).json()
    assert r["padrao"] is True
    assert r["arquivos"] == [{"caminho": "cap_001.md", "sugerido": True}, {"caminho": "README.md", "sugerido": False}]


def test_adicionar_livro_cria_e_prepara(com_pastas, projeto):
    origem = str(com_pastas.casa / "Documentos/livros/meu_livro/vol1")
    r = com_pastas.post("/api/livros", json={"titulo": "Meu Livro", "origem": origem, "arquivos": ["cap_001.md"],
                                             "personagens": ["Ana"]})
    assert r.status_code == 200 and r.json()["slug"] == "meu-livro"
    com_pastas.tarefas.aguardar(5)
    roteiro = (projeto / "livros" / "meu-livro" / "roteiro" / "cap_001.txt").read_text(encoding="utf-8")
    assert roteiro == "Ana: Oi.\n\nNarrador: A porta bateu."
    assert (projeto / "livros" / "meu-livro" / "manifesto" / "cap_001.json").exists()
    assert com_pastas.post("/api/livros", json={"titulo": "Meu Livro", "origem": origem, "arquivos": ["cap_001.md"]}).status_code == 400


def test_chaves_lista_provedores(projeto):
    def fabrica(nome):
        if nome == "openrouter":
            raise ErroConfig("defina OPENROUTER_API_KEY no .env")
        return Falso()

    with TestClient(criar_app(projeto, fabrica_provedor=fabrica)) as c:
        chaves = {k["provedor"]: k for k in c.get("/api/chaves").json()}
    assert chaves["heygen"]["situacao"] == "ok"
    assert chaves["openrouter"]["situacao"] == "ausente" and chaves["openrouter"]["bloqueia"]


def test_chaves_conferencia_online_fica_em_cache(projeto):
    class Conferido(Falso):
        conferencias = 0

        def verificar(self):
            Conferido.conferencias += 1
            from dublandio.tts import Verificacao
            return Verificacao("ok")

    with TestClient(criar_app(projeto, fabrica_provedor=lambda nome: Conferido())) as c:
        c.get("/api/chaves")
        c.get("/api/chaves")
        assert Conferido.conferencias == 2  # um por provedor, só na primeira vez
        c.get("/api/chaves?atualizar=true")
        assert Conferido.conferencias == 4


def test_cota_esgotada_na_sintese_aparece_nas_chaves(projeto):
    class SemCota(Falso):
        def sintetizar(self, texto, voz, idioma):
            raise ErroTTS("used all", interromper=True, motivo="cota")

    app = criar_app(projeto, fabrica_provedor=lambda nome: SemCota(), juntar=juntar_falso, espera=0)
    with TestClient(app) as c:
        c.tarefas = app.state.tarefas
        rodar(c, "separar")
        rodar(c, "sintetizar")
        heygen = next(k for k in c.get("/api/chaves").json() if k["provedor"] == "heygen")
    assert heygen["situacao"] == "cota" and heygen["bloqueia"]


@pytest.fixture
def com_chave(projeto, monkeypatch):
    """App cuja HeyGen aceita só a chave "boa", lida do ambiente como na fábrica real."""
    import os

    from dublandio.tts import Verificacao

    monkeypatch.setenv("HEYGEN_API_KEY", "velha")  # o monkeypatch restaura o ambiente no fim

    class PelaChave(Falso):
        def verificar(self):
            return Verificacao("ok" if os.environ.get("HEYGEN_API_KEY") == "boa" else "invalida")

    with TestClient(criar_app(projeto, fabrica_provedor=lambda nome: PelaChave())) as c:
        yield c


def test_salvar_chave_grava_no_env_e_ja_vale(com_chave, projeto):
    import os

    r = com_chave.put("/api/chaves/heygen", json={"chave": "  boa\n"})
    assert r.status_code == 200, r.text
    assert r.json()["situacao"] == "ok" and r.json()["final"] == "boa"
    assert "HEYGEN_API_KEY=boa" in (projeto / ".env").read_text(encoding="utf-8")
    assert os.environ["HEYGEN_API_KEY"] == "boa"


def test_chave_recusada_nao_e_salva(com_chave, projeto):
    import os

    r = com_chave.put("/api/chaves/heygen", json={"chave": "errada"})
    assert r.status_code == 400 and "nada foi salvo" in r.json()["detail"]
    assert not (projeto / ".env").exists()
    assert os.environ["HEYGEN_API_KEY"] == "velha"


@pytest.mark.parametrize("chave", ["", "com espaço", "a\nb"])
def test_chave_com_espaco_e_recusada(com_chave, chave):
    assert com_chave.put("/api/chaves/heygen", json={"chave": chave}).status_code == 400


def test_salvar_chave_provedor_desconhecido(com_chave):
    assert com_chave.put("/api/chaves/nada", json={"chave": "x"}).status_code == 404


# ---------- vídeos: um avatar por personagem ----------

def test_videos_lista_personagens_e_cria_avatar(cliente):
    import base64
    rodar(cliente, "separar")
    dados = cliente.get("/api/livros/ex/videos").json()
    assert dados["capitulos"][0]["personagens"] == ["Fonoti", "Kamille", "Narrador"]
    assert all(p["avatar"] is None for p in dados["personagens"])
    foto = base64.b64encode(b"\x89PNG\r\n\x1a\nfoto").decode()
    r = cliente.post("/api/livros/ex/videos/avatares", json={"personagem": "Kamille", "nome": "Kamille",
                                                               "idade": "20", "imagens": [foto]})
    assert r.status_code == 200, r.text
    ident = r.json()["id"]
    assert r.json()["idade"] == "20"
    assert cliente.get(f"/api/livros/ex/videos/avatares/{ident}").status_code == 200
    assert cliente.get(f"/api/livros/ex/videos/imagens/{r.json()['principal']}").status_code == 200
    # A mesma imagem não pode virar avatar de outro personagem.
    r = cliente.put("/api/livros/ex/videos/personagens/Narrador", json={"avatar": ident})
    assert r.status_code == 400
    assert "Kamille" in r.json()["detail"]
    dados = cliente.get("/api/livros/ex/videos").json()
    assert {p["personagem"]: p["avatar"] for p in dados["personagens"]}["Kamille"] == ident


def test_gerar_video_sem_avatar_de_todos_responde_400(cliente, projeto, monkeypatch):
    import base64
    monkeypatch.setenv("HF_TOKEN", "hf_teste")
    from dublandio.audio import pcm_to_wav
    rodar(cliente, "separar")
    monkeypatch.setattr("dublandio.avatares.segmentos",
                        lambda lv, cap: [("Fonoti", 0, 10), ("Kamille", 10, 10), ("Narrador", 20, 10)])
    (projeto / "livros/ex/audio").mkdir(parents=True)
    (projeto / "livros/ex/audio/cap_001.wav").write_bytes(pcm_to_wav(b"\0\0" * 30, rate=8000))
    foto = base64.b64encode(b"\x89PNG\r\n\x1a\nfoto").decode()
    cliente.post("/api/livros/ex/videos/avatares", json={"personagem": "Narrador", "imagens": [foto]})
    r = cliente.post("/api/livros/ex/videos/tarefas", json={"cap": "cap_001"})
    assert r.status_code == 400
    assert "Fonoti, Kamille" in r.json()["detail"]


def test_imagem_ia_sem_chave_responde_400(cliente, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = cliente.post("/api/livros/ex/videos/avatares/imagem-ia", json={"personagem": "Narrador", "nome": "N"})
    assert r.status_code == 400
    assert "OPENAI_API_KEY" in r.json()["detail"]


def test_escolha_canonica_atualiza_manifestos_sem_sintese(cliente, projeto, provedor):
    cliente.post('/api/livros/ex/tarefas', json={'etapa': 'separar'})
    cliente.tarefas.aguardar(5)
    r = cliente.put('/api/livros/ex/voz', json={'personagem': 'Ele', 'voz': 'nova', 'provedor': 'heygen'})
    assert r.status_code == 200, r.text
    livro = cliente.get('/api/livros/ex').json()
    assert livro['mapa_vozes']['Fonoti'] == 'nova'
    assert livro['mapa_vozes']['Narrador'] == 'N'
    manifesto = json.loads((projeto / 'livros/ex/manifesto/cap_001.json').read_text())
    assert manifesto[0]['voz'] == 'nova'
    assert manifesto[1]['voz'] == 'N'
    assert '# comentário mantido' in (projeto / 'livros/ex/livro.yaml').read_text()
    assert provedor.textos == []


@pytest.mark.parametrize('pedido,codigo', [
    ({'personagem': 'Fonoti', 'voz': 'nova', 'provedor': 'openrouter'}, 409),
    ({'personagem': 'inexistente', 'voz': 'nova', 'provedor': 'heygen'}, 400),
    ({'personagem': 'Fonoti', 'voz': ' ', 'provedor': 'heygen'}, 400),
])
def test_escolha_invalida_nao_altera_livro(cliente, projeto, pedido, codigo):
    path = projeto / 'livros/ex/livro.yaml'
    antes = path.read_bytes()
    assert cliente.put('/api/livros/ex/voz', json=pedido).status_code == codigo
    assert path.read_bytes() == antes


def test_voz_propria_nova_vale_para_todos_os_capitulos(cliente, projeto):
    pasta = projeto / 'livros/ex'
    (pasta / 'roteiro/cap_002.txt').write_text('Kamille: Outro capítulo.')
    rodar(cliente, 'separar')
    resposta = cliente.put('/api/livros/ex/voz', json={'personagem': 'Kamille', 'voz': 'K', 'provedor': 'heygen'})
    assert resposta.status_code == 200
    for nome in ('cap_001', 'cap_002'):
        falas = json.loads((pasta / f'manifesto/{nome}.json').read_text())
        assert next(f for f in falas if f['personagem'] == 'Kamille')['voz'] == 'K'


def test_voz_nao_muda_durante_uma_etapa(cliente, projeto):
    import threading

    fim = threading.Event()
    cliente.tarefas.iniciar({'livro': 'ex', 'etapa': 'sintetizar'}, lambda emitir: fim.wait(5))
    path = projeto / 'livros/ex/livro.yaml'
    antes = path.read_bytes()
    try:
        resposta = cliente.put('/api/livros/ex/voz', json={'personagem': 'Narrador', 'voz': 'nova', 'provedor': 'heygen'})
        assert resposta.status_code == 409
        assert path.read_bytes() == antes
    finally:
        fim.set()
        cliente.tarefas.aguardar(5)


def test_player_fixo_e_script_disponiveis(cliente):
    html = cliente.get('/').text
    assert 'id="reprodutor"' in html
    assert html.index('src="reprodutor.js"') < html.index('src="app.js"')
    resposta = cliente.get('/reprodutor.js')
    assert resposta.status_code == 200
    assert 'class ReprodutorAudio' in resposta.text
    assert resposta.headers['cache-control'] == 'no-cache'
