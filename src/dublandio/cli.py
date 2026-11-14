"""CLI: `dublandio <comando> <livro>`. Veja `dublandio --help`."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dublandio.catalogo import carregar_catalogo, filtrar
from dublandio.config import NARRADOR, PROVEDORES, Livro, carregar_env, carregar_livro, livros_disponiveis
from dublandio.novo import criar_livro, parece_capitulo, textos_da_pasta
from dublandio.preparar import fontes, preparar_livro
from dublandio.roteiro import contar_personagens, separar_livro
from dublandio.sintetizar import cadeia_do_livro, sintetizar_livro
from dublandio.tts import ErroConfig, ErroTTS, criar_provedor
from dublandio.video import ErroVideo, HeyGenVideo, gerar, planejar, salvar_plano


def _capitulo_hf(livro: Livro, args) -> int:
    from dublandio import avatares
    from dublandio.capitulo_hf import executar_capitulo, preparar_capitulo

    for item in args.avatar or []:
        personagem, sep, caminho = item.partition('=')
        if not sep or not personagem.strip() or not caminho.strip():
            raise ValueError('--avatar espera PERSONAGEM=foto.png')
        a = avatares.criar(livro, personagem, [Path(caminho).expanduser().read_bytes()])
        print(f"Avatar de {a['personagem']}: {a['principal']}")
    cap = f'cap_{args.cap:03d}'
    mapa = avatares.mapa(livro)
    for nome in avatares.personagens_do_capitulo(livro, cap):
        print(f"  {nome:<24} {mapa[nome].name if nome in mapa else '(sem avatar)'}")
    estado, path = preparar_capitulo(livro, args.cap)
    total = estado['fontes']['total_amostras'] / estado['fontes']['taxa']
    print(f'Capítulo: {total / 60:.2f} minutos. Progresso: {path}', flush=True)
    if not args.gerar:
        print('Prévia local; use --gerar para consumir a cota incluída do Hugging Face.')
        return 0
    try:
        estado = executar_capitulo(livro, args.cap, os.getenv('HF_TOKEN', ''),
                                   ao_progredir=lambda mensagem: print(mensagem, flush=True))
    except (ErroVideo, subprocess.CalledProcessError, OSError) as e:
        print(f'✗ geração interrompida: {e}; trechos prontos preservados', file=sys.stderr)
        return 1
    prontos = sum(t['quadros'] for t in estado['trechos'] if t.get('concluido')) / estado['fontes']['taxa']
    print(f"{estado['situacao']}: {prontos:.2f}s / {total:.2f}s", flush=True)
    if estado.get('arquivo'):
        print(f"✓ {estado['arquivo']}")
    elif estado.get('cota'):
        print(f"A cota renova em {estado['cota']['renova_em']}. Rode o mesmo comando para retomar.")
        if estado.get('previa'):
            print(f"Prévia PARCIAL: {estado['previa']}")
    return 0


def _video_hf(livro: Livro, args) -> int:
    from dublandio.video_hf import gerar_video_hf

    if not args.nome or Path(args.nome).name != args.nome or args.nome in (".", ".."):
        raise ValueError("--nome deve ser apenas o nome do arquivo, sem pastas")
    destino = livro.dir / "video" / f"{args.nome}.mp4"
    try:
        final = gerar_video_hf(Path(args.avatar), Path(args.audio), destino,
                              os.getenv("HF_TOKEN", ""), space=args.space)
    except (ErroVideo, subprocess.CalledProcessError, OSError) as e:
        print(f"✗ vídeo Hugging Face interrompido: {e}", file=sys.stderr)
        return 1
    print(f"✓ {final}")
    return 0


def _videos(livro: Livro, args) -> int:
    trechos = planejar(livro, args.cap)
    plano = salvar_plano(livro, trechos)
    print(f"{len(trechos)} trecho(s), {sum(t.duracao for t in trechos) / 60:.1f} min de áudio original; plano: {plano}")
    faltam = sorted({t.personagem for t in trechos if not t.avatar.strip()})
    if faltam:
        print(f"Avatares pendentes: {', '.join(faltam)}")
    if not args.gerar:
        print("Prévia local, sem gastar crédito. Após revisar o plano, use --gerar para enviar ao HeyGen.")
        return 0
    if faltam:
        raise ValueError("preencha avatares no livro.yaml antes de gerar")
    chave = os.getenv("HEYGEN_API_KEY")
    if not chave:
        raise ErroConfig("HEYGEN_API_KEY não definida no .env")
    try:
        for final in gerar(livro, trechos, HeyGenVideo(chave)):
            print(f"✓ {final}")
    except (ErroVideo, subprocess.CalledProcessError, OSError) as e:
        print(f"✗ vídeo interrompido: {e}; progresso preservado", file=sys.stderr)
        return 1
    return 0


def _preparar(livro: Livro, args) -> int:
    escritos = preparar_livro(livro, forcar=args.forcar)
    print(f"{len(escritos)} roteiro(s) escrito(s) em {livro.dir_roteiro}")
    if not args.forcar:
        print("(roteiros existentes foram mantidos; use --forcar para refazer)")
    return 0


def _separar(livro: Livro, args) -> int:
    gerados = separar_livro(livro)
    print(f"{len(gerados)} manifesto(s) em {livro.dir_manifesto}")
    return 0


def _sintetizar(livro: Livro, args) -> int:
    cadeia, avisos = cadeia_do_livro(livro, criar_provedor)
    for aviso in avisos:
        print(f"! {aviso}")
    try:
        resultados = sintetizar_livro(
            livro, cadeia, caps=args.cap,
            ao_progredir=lambda fala, estado: print(f"  [{fala.ordem:03d}] {fala.personagem}: {estado}"),
            ao_trocar=lambda de, para, motivo: print(f"↪ {de} parou ({motivo}); seguindo com {para}"),
        )
    except ErroTTS as e:  # só os que pedem `interromper`, sem reserva que sobre, chegam aqui
        print(f"✗ síntese interrompida: {e}")
        return 1
    if not resultados:
        print("nenhum manifesto para sintetizar (rode `separar` antes)")
        return 1
    houve_falha = False
    for r in resultados:
        resumo = f"{r.cap}: {r.geradas} gerada(s), {r.reusadas} do cache"
        if r.falhas:
            houve_falha = True
            print(f"✗ {resumo}, {len(r.falhas)} falha(s) — capítulo NÃO montado")
            for fala, erro in r.falhas:
                print(f"    fala {fala.ordem} ({fala.personagem}): {erro}")
        elif r.arquivo is None:
            print(f"- {r.cap}: manifesto sem falas, nada a montar")
        else:
            print(f"✓ {resumo} -> {r.arquivo}")
    if houve_falha:
        print("Rode o mesmo comando de novo: só as falas que faltam serão sintetizadas.")
    return 1 if houve_falha else 0


def _tudo(livro: Livro, args) -> int:
    if livro.origem is not None:
        args.forcar = False
        _preparar(livro, args)
    _separar(livro, args)
    return _sintetizar(livro, args)


def _vozes(livro: Livro, args) -> int:
    contagem = contar_personagens(livro)
    if not contagem:
        print("nenhum manifesto ainda (rode `separar` antes)")
        return 0
    print(f"Provedor: {livro.provedor}\n")
    for nome, n in contagem.most_common():
        voz = livro.voz(nome)
        marca = "" if nome == NARRADOR or livro.tem_voz_propria(nome) else "  (sem voz própria: usa a do Narrador)"
        print(f"{n:6d}  {nome:<24} {voz}{marca}")
    return 0


def _catalogo(args) -> int:
    vozes, _ = carregar_catalogo(args.provedor, criar_provedor, atualizar=args.atualizar)
    vozes = filtrar(vozes, args.idioma)
    for v in vozes:
        print(f"{v.id:<34} {v.genero:<7} {v.idioma:<14} {v.nome}")
    print(f"\n{len(vozes)} voz(es). Ouça as amostras em `dublandio gui`, aba Catálogo.")
    return 0


def _novo(args) -> int:
    pasta = Path(args.pasta).expanduser()
    arquivos = args.arquivos
    if arquivos is None and not any(p.suffix in (".md", ".txt") for p in pasta.glob("cap_[0-9][0-9][0-9].*")):
        arquivos = [a for a in textos_da_pasta(pasta) if parece_capitulo(a)]  # sem o padrão cap_NNN: ordem natural
    livro = criar_livro(
        Path("."), args.titulo or pasta.name.replace("_", " ").replace("-", " ").title(), pasta, arquivos,
        provedor=args.provedor, reserva=args.reserva or None, personagens=args.personagens, slug=args.slug,
    )
    print(f"livro criado: {livro.dir / 'livro.yaml'}")
    for cap, origem in fontes(livro):
        print(f"  {cap} <- {origem.relative_to(livro.origem).as_posix()}")
    print(f"Revise o livro.yaml e rode `dublandio preparar {livro.slug}`.")
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dublandio", description="Capítulos de livro -> áudio dublado.")
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("livros", help="lista os livros configurados")
    novovideo = sub.add_parser('novo-video', help='cria um projeto com roteiro, vozes e fotos, sem gerar nem cobrar')
    novovideo.add_argument('roteiro', type=Path, help='roteiro UTF-8 (.txt ou .md), com Nome: fala')
    novovideo.add_argument('--titulo', required=True)
    novovideo.add_argument('--personagens', required=True, type=Path,
                          help='YAML: Nome: {voz: ID_OU_NOME, avatar: foto.png}; fotos relativas a este YAML')
    novovideo.add_argument('--provedor', choices=PROVEDORES, default='heygen')
    novo = sub.add_parser("novo", help="adiciona um livro a partir de uma pasta com capítulos .md ou .txt")
    novo.add_argument("pasta", help="pasta com cap_NNN.md/.txt (ou outros textos, com --arquivos)")
    novo.add_argument("--titulo", help="padrão: o nome da pasta")
    novo.add_argument("--slug", help="nome da pasta em livros/ (padrão: tirado do título)")
    novo.add_argument("--provedor", default="heygen", choices=PROVEDORES)
    novo.add_argument("--reserva", default="openrouter", help='provedor reserva; "" para nenhum')
    novo.add_argument("--personagens", nargs="+", help="nomes que ajudam o preparar a achar quem fala")
    novo.add_argument("--arquivos", nargs="+", help="capítulos em ordem, relativos à pasta (vira cap_001, cap_002...)")
    cat = sub.add_parser("catalogo", help="lista as vozes que o provedor oferece (não gasta crédito)")
    cat.add_argument("provedor", nargs="?", default="heygen", choices=PROVEDORES)
    cat.add_argument("--idioma", help='filtra por idioma (ex.: pt, Portuguese, Multilingual)')
    cat.add_argument("--atualizar", action="store_true", help="busca de novo em vez de usar o cache de um dia")
    gui = sub.add_parser("gui", help="abre a interface no navegador (http://127.0.0.1:8765)")
    gui.add_argument("--porta", type=int, default=8765)
    gui.add_argument("--host", default="127.0.0.1", help="endereço de escuta (0.0.0.0 dentro do Docker)")
    gui.add_argument("--sem-navegador", action="store_true", help="não abre o navegador sozinho")

    def com_livro(nome: str, ajuda: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(nome, help=ajuda)
        sp.add_argument("livro", help="pasta em livros/ (ex.: o-louco-e-o-bruxo)")
        return sp

    com_livro("preparar", "gera roteiros a partir dos .md de origem").add_argument(
        "--forcar", action="store_true", help="sobrescreve roteiros existentes (perde edições manuais)")
    com_livro("separar", "gera os manifestos a partir dos roteiros")
    for nome, ajuda in (("sintetizar", "gera o áudio dos capítulos"), ("tudo", "preparar + separar + sintetizar")):
        com_livro(nome, ajuda).add_argument("--cap", type=int, nargs="+", help="só estes capítulos (ex.: --cap 1 2)")
    com_livro("vozes", "mostra personagens, nº de falas e a voz de cada um")
    videos = com_livro("videos", "planeja vídeos usando os áudios existentes; --gerar envia ao HeyGen")
    videos.add_argument("--cap", type=int, nargs="+", help="só estes capítulos")
    videos.add_argument("--gerar", action="store_true", help="gera clipes no HeyGen (gasta crédito) e monta o MP4")
    hf = com_livro("video-hf", "anima uma foto com áudio existente em uma demo pública SadTalker")
    hf.add_argument("--avatar", required=True, help="imagem local do avatar")
    hf.add_argument("--audio", required=True, help="WAV já gerado")
    hf.add_argument("--nome", default="teste-huggingface", help="nome do MP4 dentro da pasta video/ do livro")
    hf.add_argument("--space", default="henrybit/SadTalker-Demo", help="Space com API SadTalker compatível (/generate)")
    caphf = com_livro('capitulo-hf', 'gera um capítulo WAV em partes, retomando pela cota diária do Hugging Face')
    caphf.add_argument('--cap', required=True, type=int, help='número do capítulo em audio/cap_NNN.wav')
    caphf.add_argument('--avatar', action='append', metavar='PERSONAGEM=FOTO',
                       help='cria um avatar novo para o personagem neste livro (repita para cada um)')
    caphf.add_argument('--gerar', action='store_true', help='usa a cota incluída; sem esta opção, só prepara o progresso local')
    return p


_COMANDOS = {"preparar": _preparar, "separar": _separar, "sintetizar": _sintetizar, "tudo": _tudo, "vozes": _vozes, "videos": _videos, "video-hf": _video_hf, "capitulo-hf": _capitulo_hf}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    carregar_env(Path(".env"))
    if args.comando == "livros":
        for slug in livros_disponiveis():
            print(slug)
        return 0
    if args.comando == 'novo-video':
        import yaml
        from dublandio.projeto_video import criar_projeto

        try:
            dados = yaml.safe_load(args.personagens.read_text(encoding='utf-8-sig'))
            if not isinstance(dados, dict) or not dados:
                raise ValueError('o YAML deve listar Nome: {voz: ID_OU_NOME, avatar: foto.png}')
            fichas = []
            for nome, ficha in dados.items():
                if (not isinstance(nome, str) or not isinstance(ficha, dict)
                        or not isinstance(ficha.get('voz'), str) or not isinstance(ficha.get('avatar'), str)):
                    raise ValueError('cada personagem deve ter voz e avatar em texto')
                foto = args.personagens.parent / Path(ficha['avatar']).expanduser()
                fichas.append({'nome': nome, 'voz': ficha['voz'], 'avatar': foto.read_bytes()})
            lv = criar_projeto(Path('.'), args.titulo, args.roteiro.read_text(encoding='utf-8-sig'), fichas, args.provedor)
        except (OSError, ValueError, yaml.YAMLError) as e:
            print(f'erro: {e}', file=sys.stderr)
            return 2
        print(f'Projeto criado: {lv.slug}. Abra a aba Vídeos na interface para gerar áudio e animação.')
        return 0
    if args.comando == "novo":
        try:
            return _novo(args)
        except (FileNotFoundError, ValueError) as e:
            print(f"erro: {e}", file=sys.stderr)
            return 2
    if args.comando == "catalogo":
        try:
            return _catalogo(args)
        except (ErroConfig, ErroTTS) as e:
            print(f"erro: {e}", file=sys.stderr)
            return 2
    if args.comando == "gui":
        from dublandio.gui.servidor import rodar  # só carrega FastAPI quando precisa

        rodar(porta=args.porta, abrir=not args.sem_navegador, host=args.host)
        return 0
    try:
        livro = carregar_livro(args.livro)
        return _COMANDOS[args.comando](livro, args)
    except (FileNotFoundError, ValueError, KeyError, ErroConfig) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
